"""Public API for OpenFOAM web: jobs, files, and delegation to the runner service."""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import re

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pydantic import BaseModel, Field

from app.mongo_store import (
    connect_mongo,
    instruction_doc,
    instruction_to_api,
    job_doc,
    jobs_collection,
    row_to_api,
    run_instructions_collection,
    simulation_doc,
    simulation_to_api,
    simulations_collection,
)

JOBS_ROOT = Path(os.environ.get("JOBS_ROOT", "/jobs")).resolve()
RUNNER_URL = os.environ.get("RUNNER_URL", "http://openfoam-runner:8080").rstrip("/")
# Browsers treat http://127.0.0.1:3000 and http://localhost:3000 as different origins — allow both by default.
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = await connect_mongo()
    app.state.mongo_client = client
    app.state.jobs: AsyncIOMotorCollection = jobs_collection(client)
    app.state.run_instructions: AsyncIOMotorCollection = run_instructions_collection(client)
    app.state.simulations: AsyncIOMotorCollection = simulations_collection(client)
    templates_dir = JOBS_ROOT / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield
    finally:
        client.close()


class RunInstructionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    commands: str = Field(min_length=1, max_length=50_000)
    description: str = Field(default="", max_length=10_000)


class RunInstructionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    commands: str | None = Field(default=None, min_length=1, max_length=50_000)
    description: str | None = Field(default=None, max_length=10_000)


app = FastAPI(title="OpenFOAM Web API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_TIME_DIR_RE = re.compile(r"^\d+(\.\d+)?$")
_RUNNING_RE = re.compile(r"^Running\s+([^\s]+)\s+on\s+", re.MULTILINE)
_TIME_LINE_RE = re.compile(r"^\s*Time\s*=\s*([0-9]+(\.[0-9]+)?)\s*$", re.MULTILINE)


def _ws_progress_from_chunk(
    chunk: str,
    current_phase: str | None,
    current_time: str | None,
) -> tuple[str | None, str | None]:
    m = None
    for m in _RUNNING_RE.finditer(chunk):
        pass
    if m:
        current_phase = m.group(1)

    t = None
    for t in _TIME_LINE_RE.finditer(chunk):
        pass
    if t:
        current_time = t.group(1)

    return current_phase, current_time


async def _read_job_status(job_id: str) -> str:
    coll: AsyncIOMotorCollection = app.state.jobs
    doc = await coll.find_one({"_id": job_id}, projection={"status": 1})
    return doc["status"] if doc else "unknown"


async def _tail_text_file(path: Path, offset: int) -> tuple[str, int]:
    def _read() -> tuple[str, int]:
        if not path.is_file():
            return "", offset
        with path.open("rb") as f:
            f.seek(max(0, offset))
            data = f.read()
            new_offset = f.tell()
        try:
            return data.decode("utf-8", errors="replace"), new_offset
        except Exception:
            return data.decode(errors="replace"), new_offset

    return await asyncio.to_thread(_read)


def _openfoam_case_root(extract_dir: Path) -> Path:
    """ZIP root may wrap the case (e.g. DPMFoam/Goldschmidt). Prefer root if it has controlDict."""
    if not extract_dir.is_dir():
        return extract_dir
    if (extract_dir / "system" / "controlDict").is_file():
        return extract_dir
    candidates: list[tuple[int, Path]] = []
    try:
        for p in extract_dir.rglob("controlDict"):
            if p.parent.name != "system" or not p.is_file():
                continue
            root = p.parent.parent
            try:
                depth = len(root.relative_to(extract_dir).parts)
            except ValueError:
                continue
            candidates.append((depth, root))
    except OSError:
        return extract_dir
    if not candidates:
        return extract_dir
    candidates.sort(key=lambda x: (x[0], str(x[1])))
    return candidates[0][1]


def _list_time_dirs(case_dir: Path) -> list[str]:
    if not case_dir.is_dir():
        return []
    out: list[str] = []
    for p in case_dir.iterdir():
        if p.is_dir() and _TIME_DIR_RE.match(p.name):
            out.append(p.name)
    out.sort(key=lambda s: float(s))
    return out


def _detect_regions(case_dir: Path) -> list[str]:
    rp = case_dir / "constant" / "regionProperties"
    if not rp.is_file():
        return []
    txt = rp.read_text(encoding="utf-8", errors="replace")
    regions: set[str] = set()
    for m in re.finditer(r"\(\s*([A-Za-z0-9_]+)\s*\)", txt):
        regions.add(m.group(1))
    return sorted(regions)


def _ensure_case_foam_marker(case_dir: Path) -> None:
    """ParaView expects an empty *.foam file at the case root; create case.foam if missing."""
    if not case_dir.is_dir():
        return
    marker = case_dir / "case.foam"
    if marker.is_file():
        return
    try:
        marker.write_text("", encoding="utf-8")
    except OSError:
        pass


@app.get("/api/jobs/{job_id}/outputs")
async def get_job_outputs(job_id: str) -> dict:
    await get_job(job_id)
    case_dir = JOBS_ROOT / job_id / "case"
    await asyncio.to_thread(_ensure_case_foam_marker, case_dir)

    def _outputs() -> tuple[list[str], list[str], bool, bool]:
        of_root = _openfoam_case_root(case_dir)
        times = _list_time_dirs(of_root)
        regions = _detect_regions(of_root)
        has_vtk = (of_root / "VTK").is_dir()
        has_foam = any(case_dir.glob("*.foam")) or any(of_root.glob("*.foam"))
        return times, regions, has_vtk, has_foam

    times, regions, has_vtk, has_foam = await asyncio.to_thread(_outputs)
    return {"job_id": job_id, "times": times, "regions": regions, "has_vtk": has_vtk, "has_foam": bool(has_foam)}


@app.get("/health")
async def health() -> dict[str, str]:
    client: AsyncIOMotorClient = app.state.mongo_client
    await client.admin.command("ping")
    return {"status": "ok", "runner_url": RUNNER_URL, "mongodb": "ok"}


@app.get("/api/run-instructions")
async def list_run_instructions() -> dict:
    coll: AsyncIOMotorCollection = app.state.run_instructions
    cursor = coll.find({}, projection={"_id": 0}).sort("created_at", -1).limit(500)
    rows = await cursor.to_list(length=500)
    return {"run_instructions": [instruction_to_api(r) for r in rows if instruction_to_api(r)]}


@app.get("/api/run-instructions/{instruction_id}")
async def get_run_instruction(instruction_id: str) -> dict:
    coll: AsyncIOMotorCollection = app.state.run_instructions
    doc = await coll.find_one({"_id": instruction_id})
    out = instruction_to_api(doc)
    if not out:
        raise HTTPException(status_code=404, detail="Run instruction not found")
    return out


@app.post("/api/run-instructions")
async def create_run_instruction(body: RunInstructionCreate) -> dict:
    coll: AsyncIOMotorCollection = app.state.run_instructions
    instruction_id = str(uuid.uuid4())
    now = _utc_now()
    doc = instruction_doc(
        instruction_id,
        name=body.name.strip(),
        commands=body.commands,
        description=(body.description or "").strip(),
        created_at=now,
        updated_at=now,
    )
    await coll.insert_one(doc)
    api_doc = instruction_to_api(doc)
    assert api_doc is not None
    return api_doc


@app.patch("/api/run-instructions/{instruction_id}")
async def update_run_instruction(instruction_id: str, body: RunInstructionUpdate) -> dict:
    coll: AsyncIOMotorCollection = app.state.run_instructions
    existing = await coll.find_one({"_id": instruction_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Run instruction not found")
    updates: dict[str, str] = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.commands is not None:
        updates["commands"] = body.commands
    if body.description is not None:
        updates["description"] = body.description.strip()
    if not updates:
        out0 = instruction_to_api(existing)
        assert out0 is not None
        return out0
    updates["updated_at"] = _utc_now()
    await coll.update_one({"_id": instruction_id}, {"$set": updates})
    doc = await coll.find_one({"_id": instruction_id})
    out = instruction_to_api(doc)
    assert out is not None
    return out


@app.delete("/api/run-instructions/{instruction_id}")
async def delete_run_instruction(instruction_id: str) -> dict:
    coll: AsyncIOMotorCollection = app.state.run_instructions
    r = await coll.delete_one({"_id": instruction_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Run instruction not found")
    return {"ok": True, "id": instruction_id}


# ── Simulation templates ──────────────────────────────────────────────────────

TEMPLATES_DIR = JOBS_ROOT / "templates"


def _parse_openfoam_values(text: str) -> list[dict]:
    """Extract simple key-value pairs from an OpenFOAM dictionary file."""
    results: list[dict] = []
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
            continue
        m = re.match(
            r"^([A-Za-z_][A-Za-z0-9_]*)\s+"
            r"(-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\s*;",
            stripped,
        )
        if m:
            key, val = m.group(1), m.group(2)
            if key in ("version", "format", "location", "object", "class", "note", "arch"):
                continue
            vtype = "number"
            results.append({"key": key, "value": val, "type": vtype})
            continue
        m2 = re.match(
            r'^([A-Za-z_][A-Za-z0-9_]*)\s+"?([^";]+)"?\s*;',
            stripped,
        )
        if m2:
            key, val = m2.group(1), m2.group(2).strip()
            if key in ("version", "format", "location", "object", "class", "note", "arch"):
                continue
            results.append({"key": key, "value": val, "type": "text"})
    return results


def _analyze_openfoam_zip(zip_bytes: bytes) -> dict:
    """Analyze an OpenFOAM case ZIP and return structure + discovered variables."""
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = sorted(n for n in zf.namelist() if not zf.getinfo(n).is_dir())

    prefix = ""
    for n in names:
        if n.endswith("system/controlDict"):
            prefix = n[: n.index("system/")]
            break

    def read(path: str) -> str | None:
        full = prefix + path
        if full not in names:
            return None
        try:
            return zf.read(full).decode("utf-8", errors="replace")
        except Exception:
            return None

    rel_names = [n[len(prefix):] if n.startswith(prefix) else n for n in names]

    dirs: dict[str, list[str]] = {}
    for n in rel_names:
        parts = n.split("/")
        top = parts[0] if len(parts) > 1 else "(root)"
        dirs.setdefault(top, []).append(n)

    solver = ""
    control_dict_text = read("system/controlDict")
    if control_dict_text:
        sm = re.search(r"^\s*application\s+([A-Za-z0-9_+-]+)\s*;", control_dict_text, re.MULTILINE)
        if sm:
            solver = sm.group(1)

    has_allrun = any(n.endswith("Allrun") or n == "Allrun" for n in rel_names)
    has_blockmesh = "system/blockMeshDict" in rel_names

    key_files = [
        "system/controlDict",
        "system/blockMeshDict",
        "system/fvSchemes",
        "system/fvSolution",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        "constant/thermophysicalProperties",
    ]

    time0_files = [n for n in rel_names if re.match(r"^0/[^/]+$", n)]
    key_files.extend(time0_files)

    discovered: list[dict] = []
    for fp in key_files:
        content = read(fp)
        if not content:
            continue
        vals = _parse_openfoam_values(content)
        for v in vals:
            discovered.append({
                "file": fp,
                "key": v["key"],
                "value": v["value"],
                "type": v["type"],
            })

    structure = {}
    for section, files in sorted(dirs.items()):
        structure[section] = sorted(files)[:50]

    return {
        "solver": solver,
        "has_allrun": has_allrun,
        "has_blockmesh": has_blockmesh,
        "file_count": len(rel_names),
        "structure": structure,
        "discovered_variables": discovered,
    }


@app.post("/api/simulations/analyze-zip")
async def analyze_zip(case_zip: UploadFile = File(...)) -> dict:
    raw = await case_zip.read()
    try:
        result = await asyncio.to_thread(_analyze_openfoam_zip, raw)
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="Invalid ZIP archive") from e
    return result


@app.get("/api/simulations")
async def list_simulations() -> dict:
    coll: AsyncIOMotorCollection = app.state.simulations
    cursor = coll.find({}, projection={"_id": 0}).sort("created_at", -1).limit(200)
    rows = await cursor.to_list(length=200)
    return {"simulations": [simulation_to_api(r) for r in rows if simulation_to_api(r)]}


@app.get("/api/simulations/{sim_id}")
async def get_simulation(sim_id: str) -> dict:
    coll: AsyncIOMotorCollection = app.state.simulations
    doc = await coll.find_one({"_id": sim_id})
    out = simulation_to_api(doc)
    if not out:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return out


@app.post("/api/simulations")
async def create_simulation(
    title: str = Form(...),
    description: str = Form(""),
    commands: str = Form(""),
    input_fields_json: str = Form("[]"),
    case_zip: UploadFile = File(...),
    thumbnail: UploadFile | None = File(None),
) -> dict:
    import json as _json

    sim_id = str(uuid.uuid4())
    sim_dir = TEMPLATES_DIR / sim_id
    sim_dir.mkdir(parents=True, exist_ok=True)

    zip_bytes = await case_zip.read()
    try:
        zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="Invalid ZIP archive") from e
    zip_path = sim_dir / "case.zip"
    await asyncio.to_thread(zip_path.write_bytes, zip_bytes)

    thumb_path = ""
    if thumbnail and thumbnail.filename:
        ext = Path(thumbnail.filename).suffix.lower() or ".png"
        thumb_file = sim_dir / f"thumbnail{ext}"
        thumb_bytes = await thumbnail.read()
        await asyncio.to_thread(thumb_file.write_bytes, thumb_bytes)
        thumb_path = str(thumb_file)

    try:
        fields = _json.loads(input_fields_json)
        if not isinstance(fields, list):
            fields = []
    except _json.JSONDecodeError:
        fields = []

    now = _utc_now()
    coll: AsyncIOMotorCollection = app.state.simulations
    doc = simulation_doc(
        sim_id,
        title=title.strip(),
        description=(description or "").strip(),
        commands=(commands or "").strip(),
        case_zip_path=str(zip_path),
        thumbnail_path=thumb_path,
        input_fields=fields,
        created_at=now,
        updated_at=now,
    )
    await coll.insert_one(doc)
    api_doc = simulation_to_api(doc)
    assert api_doc is not None
    return api_doc


@app.patch("/api/simulations/{sim_id}")
async def update_simulation(
    sim_id: str,
    title: str | None = Form(None),
    description: str | None = Form(None),
    commands: str | None = Form(None),
    input_fields_json: str | None = Form(None),
    thumbnail: UploadFile | None = File(None),
    case_zip: UploadFile | None = File(None),
) -> dict:
    import json as _json

    coll: AsyncIOMotorCollection = app.state.simulations
    existing = await coll.find_one({"_id": sim_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Simulation not found")

    updates: dict = {}
    if title is not None:
        updates["title"] = title.strip()
    if description is not None:
        updates["description"] = description.strip()
    if commands is not None:
        updates["commands"] = commands.strip()
    if input_fields_json is not None:
        try:
            fields = _json.loads(input_fields_json)
            if isinstance(fields, list):
                updates["input_fields"] = fields
        except _json.JSONDecodeError:
            pass

    if case_zip and case_zip.filename:
        zip_bytes = await case_zip.read()
        try:
            zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile as e:
            raise HTTPException(status_code=400, detail="Invalid ZIP archive") from e
        sim_dir = TEMPLATES_DIR / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)
        zip_path = sim_dir / "case.zip"
        await asyncio.to_thread(zip_path.write_bytes, zip_bytes)
        updates["case_zip_path"] = str(zip_path)

    if thumbnail and thumbnail.filename:
        sim_dir = TEMPLATES_DIR / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(thumbnail.filename).suffix.lower() or ".png"
        thumb_file = sim_dir / f"thumbnail{ext}"
        thumb_bytes = await thumbnail.read()
        await asyncio.to_thread(thumb_file.write_bytes, thumb_bytes)
        updates["thumbnail_path"] = str(thumb_file)

    if not updates:
        return simulation_to_api(existing)  # type: ignore[return-value]
    updates["updated_at"] = _utc_now()
    await coll.update_one({"_id": sim_id}, {"$set": updates})
    doc = await coll.find_one({"_id": sim_id})
    return simulation_to_api(doc)  # type: ignore[return-value]


@app.delete("/api/simulations/{sim_id}")
async def delete_simulation(sim_id: str) -> dict:
    import shutil

    coll: AsyncIOMotorCollection = app.state.simulations
    doc = await coll.find_one({"_id": sim_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Simulation not found")
    await coll.delete_one({"_id": sim_id})
    sim_dir = TEMPLATES_DIR / sim_id
    if sim_dir.exists():
        await asyncio.to_thread(shutil.rmtree, sim_dir, ignore_errors=True)
    return {"ok": True, "id": sim_id}


@app.get("/api/simulations/{sim_id}/case-analysis")
async def analyze_simulation_stored_case(sim_id: str) -> dict:
    """Return the same shape as POST /api/simulations/analyze-zip for the template's stored case.zip."""
    coll: AsyncIOMotorCollection = app.state.simulations
    doc = await coll.find_one({"_id": sim_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Simulation not found")
    zip_path = Path(doc.get("case_zip_path") or "")
    if not zip_path.is_file():
        raise HTTPException(status_code=404, detail="Template case ZIP not found")
    raw = await asyncio.to_thread(zip_path.read_bytes)
    try:
        return await asyncio.to_thread(_analyze_openfoam_zip, raw)
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="Invalid stored ZIP archive") from e


@app.get("/api/simulations/{sim_id}/thumbnail")
async def get_simulation_thumbnail(sim_id: str) -> FileResponse:
    coll: AsyncIOMotorCollection = app.state.simulations
    doc = await coll.find_one({"_id": sim_id}, projection={"thumbnail_path": 1})
    if not doc or not doc.get("thumbnail_path"):
        raise HTTPException(status_code=404, detail="No thumbnail")
    p = Path(doc["thumbnail_path"])
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Thumbnail file missing")
    return FileResponse(p)


@app.post("/api/simulations/{sim_id}/run")
async def run_simulation(
    sim_id: str,
    background_tasks: BackgroundTasks,
    body: dict | None = None,
) -> dict:
    """Create a job from a simulation template, optionally overriding input fields."""
    coll: AsyncIOMotorCollection = app.state.simulations
    doc = await coll.find_one({"_id": sim_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Simulation not found")

    zip_path = Path(doc["case_zip_path"])
    if not zip_path.is_file():
        raise HTTPException(status_code=500, detail="Template case ZIP missing from storage")

    overrides: dict = (body or {}).get("inputs", {}) if body else {}

    job_id = str(uuid.uuid4())
    job_dir = JOBS_ROOT / job_id
    case_dir = job_dir / "case"
    case_dir.mkdir(parents=True, exist_ok=True)

    raw = await asyncio.to_thread(zip_path.read_bytes)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(case_dir)
    await asyncio.to_thread(_ensure_case_foam_marker, case_dir)

    resolved_commands = (doc.get("commands") or "").strip()
    # 3D viewer (Trame) lists case/VTK/; ensure post-processing unless the user opted out.
    if resolved_commands and not re.search(r"(?<![\w/])foamToVTK(?!\w)", resolved_commands, re.IGNORECASE):
        resolved_commands = f"{resolved_commands} && foamToVTK"

    now = _utc_now()
    jobs_coll: AsyncIOMotorCollection = app.state.jobs
    await jobs_coll.insert_one(
        job_doc(
            job_id,
            status="pending",
            commands=resolved_commands,
            created_at=now,
            updated_at=now,
            run_instruction_id=None,
            run_instruction_name=doc.get("title"),
            simulation_id=sim_id,
        )
    )

    background_tasks.add_task(_run_job, job_id, resolved_commands)
    return {"id": job_id, "status": "pending", "simulation_id": sim_id}


@app.post("/api/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    case_zip: UploadFile = File(...),
    commands: str = Form(""),
    run_instruction_id: str | None = Form(None),
) -> dict:
    if not case_zip.filename:
        raise HTTPException(status_code=400, detail="Missing case_zip file")

    ri_id: str | None = (run_instruction_id or "").strip() or None
    ri_name: str | None = None
    resolved_commands = (commands or "").strip()
    if ri_id:
        icoll: AsyncIOMotorCollection = app.state.run_instructions
        inst = await icoll.find_one({"_id": ri_id})
        if not inst:
            raise HTTPException(status_code=400, detail="run_instruction_id not found")
        ri_name = inst.get("name")
        if not resolved_commands:
            resolved_commands = (inst.get("commands") or "").strip()
    if not resolved_commands:
        raise HTTPException(
            status_code=400,
            detail="commands is required (or provide run_instruction_id and leave commands empty to use saved commands)",
        )

    if not re.search(r"(?<![\w/])foamToVTK(?!\w)", resolved_commands, re.IGNORECASE):
        resolved_commands = f"{resolved_commands} && foamToVTK"

    job_id = str(uuid.uuid4())
    job_dir = JOBS_ROOT / job_id
    case_dir = job_dir / "case"
    case_dir.mkdir(parents=True, exist_ok=True)

    raw = await case_zip.read()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            zf.extractall(case_dir)
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="Invalid ZIP archive") from e

    await asyncio.to_thread(_ensure_case_foam_marker, case_dir)

    now = _utc_now()
    coll: AsyncIOMotorCollection = app.state.jobs
    await coll.insert_one(
        job_doc(
            job_id,
            status="pending",
            commands=resolved_commands,
            created_at=now,
            updated_at=now,
            run_instruction_id=ri_id,
            run_instruction_name=ri_name,
        )
    )

    background_tasks.add_task(_run_job, job_id, resolved_commands)
    return {"id": job_id, "status": "pending"}


async def _run_job(job_id: str, commands: str) -> None:
    coll: AsyncIOMotorCollection = app.state.jobs
    now = _utc_now()
    await coll.update_one({"_id": job_id}, {"$set": {"status": "running", "updated_at": now}})

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(86400.0)) as client:
            r = await client.post(
                f"{RUNNER_URL}/internal/run",
                json={"job_id": job_id, "commands": commands},
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code >= 400:
                err = data.get("detail", r.text[:2000])
                await coll.update_one(
                    {"_id": job_id},
                    {"$set": {"status": "failed", "error_message": str(err), "updated_at": _utc_now()}},
                )
                return

            rc = data.get("returncode", -1)
            log_path = data.get("log_path")
            st = "completed" if rc == 0 else "failed"
            await coll.update_one(
                {"_id": job_id},
                {
                    "$set": {
                        "status": st,
                        "returncode": rc,
                        "runner_log_path": log_path,
                        "updated_at": _utc_now(),
                    }
                },
            )
    except Exception as e:  # noqa: BLE001
        await coll.update_one(
            {"_id": job_id},
            {"$set": {"status": "failed", "error_message": str(e), "updated_at": _utc_now()}},
        )


@app.get("/api/jobs")
async def list_jobs() -> dict:
    coll: AsyncIOMotorCollection = app.state.jobs
    cursor = coll.find({}, projection={"_id": 0}).sort("created_at", -1).limit(200)
    rows = await cursor.to_list(length=200)
    return {"jobs": [row_to_api(r) for r in rows if row_to_api(r)]}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    coll: AsyncIOMotorCollection = app.state.jobs
    doc = await coll.find_one({"_id": job_id})
    out = row_to_api(doc)
    if not out:
        raise HTTPException(status_code=404, detail="Job not found")
    return out


@app.get("/api/jobs/{job_id}/log")
async def get_job_log(job_id: str) -> dict:
    await get_job(job_id)
    log_path = JOBS_ROOT / job_id / "openfoam.log"
    if not log_path.is_file():
        return {"log": "", "path": str(log_path)}
    text = await asyncio.to_thread(log_path.read_text, encoding="utf-8", errors="replace")
    return {"log": text, "path": str(log_path)}


@app.websocket("/api/jobs/{job_id}/ws")
async def job_ws(job_id: str, ws: WebSocket) -> None:
    await ws.accept()
    try:
        job = await get_job(job_id)
    except HTTPException:
        await ws.send_json({"type": "error", "detail": "Job not found"})
        await ws.close(code=1008)
        return

    log_path = JOBS_ROOT / job_id / "openfoam.log"
    offset = 0
    if log_path.is_file():
        try:
            offset = max(0, log_path.stat().st_size - 200_000)
        except Exception:
            offset = 0

    status = job.get("status", "unknown")
    phase: str | None = None
    tcur: str | None = None

    await ws.send_json({"type": "hello", "job_id": job_id, "status": status, "offset": offset})

    chunk, offset = await _tail_text_file(log_path, offset)
    if chunk:
        phase, tcur = _ws_progress_from_chunk(chunk, phase, tcur)
        await ws.send_json({"type": "log", "chunk": chunk, "offset": offset})
        await ws.send_json({"type": "progress", "phase": phase, "time": tcur, "status": status})

    idle_ticks = 0
    while True:
        try:
            await asyncio.wait_for(ws.receive_text(), timeout=0.01)
        except asyncio.TimeoutError:
            pass
        except WebSocketDisconnect:
            return
        except Exception:
            pass

        chunk, offset2 = await _tail_text_file(log_path, offset)
        if chunk:
            offset = offset2
            phase, tcur = _ws_progress_from_chunk(chunk, phase, tcur)
            await ws.send_json({"type": "log", "chunk": chunk, "offset": offset})
            status = await _read_job_status(job_id)
            await ws.send_json({"type": "progress", "phase": phase, "time": tcur, "status": status})
            idle_ticks = 0
        else:
            idle_ticks += 1
            if idle_ticks % 50 == 0:
                status = await _read_job_status(job_id)
                await ws.send_json({"type": "progress", "phase": phase, "time": tcur, "status": status})

            if idle_ticks > 20:
                status = await _read_job_status(job_id)
                if status in ("completed", "failed"):
                    job = await get_job(job_id)
                    await ws.send_json(
                        {
                            "type": "done",
                            "status": status,
                            "returncode": job.get("returncode"),
                            "error": job.get("error_message"),
                        }
                    )
                    await ws.close(code=1000)
                    return

        await asyncio.sleep(0.25)


def _unlink_quiet(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _zip_job_to_temp_path(job_id: str) -> str:
    """Write job workspace to a temp zip on disk (avoids holding the whole archive in RAM).

    Skips ``processor*`` directories: they duplicate decomposed fields and routinely blow
    memory/disk when zipped with the reconstructed case.
    """
    root = (JOBS_ROOT / job_id).resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="Job workspace missing")
    case = root / "case"
    if case.is_dir():
        _ensure_case_foam_marker(case)

    fd, out_path = tempfile.mkstemp(prefix="jobzip-", suffix=".zip")
    os.close(fd)
    try:
        # STORED: mostly-binary OpenFOAM barely compresses; avoids zlib peaks on huge files.
        with zipfile.ZipFile(
            out_path, "w", zipfile.ZIP_STORED, allowZip64=True
        ) as zf:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                dirp = Path(dirpath)
                dirnames[:] = [d for d in dirnames if not d.startswith("processor")]
                for name in sorted(filenames):
                    fp = dirp / name
                    if not fp.is_file():
                        continue
                    arc = fp.relative_to(root)
                    zf.write(fp, arcname=str(arc))
    except Exception:
        _unlink_quiet(out_path)
        raise
    return out_path


@app.get("/api/jobs/{job_id}/download")
async def download_job(job_id: str) -> FileResponse:
    await get_job(job_id)
    out_path = await asyncio.to_thread(_zip_job_to_temp_path, job_id)
    return FileResponse(
        out_path,
        media_type="application/zip",
        filename=f"{job_id}.zip",
        background=BackgroundTask(_unlink_quiet, out_path),
    )


@app.get("/api/jobs/{job_id}/case/{file_path:path}")
async def get_case_file(job_id: str, file_path: str) -> FileResponse:
    await get_job(job_id)
    full = (JOBS_ROOT / job_id / "case" / file_path).resolve()
    case_root = (JOBS_ROOT / job_id / "case").resolve()
    try:
        full.relative_to(case_root)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid path") from e
    if not full.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full)
