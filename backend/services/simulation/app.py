"""Simulation microservice: jobs, simulation templates, case files, and runner orchestration."""

from __future__ import annotations

from shared.request_logging import install_request_logging
from shared.telemetry import configure_telemetry, instrument_fastapi

configure_telemetry()

import asyncio
import csv
import logging
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
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.responses import Response
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pydantic import BaseModel, Field

from services.simulation.mass_run_csv import inputs_to_overrides, parse_mass_run_csv
from services.simulation.mongo_store import (
    collect_mass_run_child_job_ids,
    connect_mongo,
    instruction_doc,
    instruction_to_api,
    job_doc,
    jobs_collection,
    mass_run_doc,
    mass_run_list_item_to_api,
    mass_run_to_api,
    mass_runs_collection,
    predictive_model_to_api,
    predictive_models_collection,
    row_to_api,
    run_instructions_collection,
    simulation_doc,
    simulation_to_api,
    simulations_collection,
)

JOBS_ROOT = Path(os.environ.get("JOBS_ROOT", "/jobs")).resolve()
RUNNER_URL = os.environ.get("RUNNER_URL", "http://forge-runner:8080").rstrip("/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = await connect_mongo()
    app.state.mongo_client = client
    app.state.jobs: AsyncIOMotorCollection = jobs_collection(client)
    app.state.run_instructions: AsyncIOMotorCollection = run_instructions_collection(client)
    app.state.simulations: AsyncIOMotorCollection = simulations_collection(client)
    app.state.mass_runs: AsyncIOMotorCollection = mass_runs_collection(client)
    app.state.predictive_models: AsyncIOMotorCollection = predictive_models_collection(client)
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


class MassRunStartBody(BaseModel):
    batch_size: int = Field(ge=1, le=64, default=1)
    runs: list[dict] = Field(min_length=1)


class PredictiveModelBody(BaseModel):
    training_mass_run_ids: list[str] = Field(default_factory=list)
    testing_mass_run_ids: list[str] = Field(default_factory=list)


app = FastAPI(
    title="Forge Simulation Service",
    version="1.0.0",
    lifespan=lifespan,
    description="Jobs, simulation templates, case files, and runner orchestration (internal; browser uses BFF).",
    openapi_tags=[
        {"name": "health", "description": "Service health"},
        {"name": "jobs", "description": "CFD job lifecycle"},
        {"name": "simulations", "description": "Simulation templates"},
        {"name": "run-instructions", "description": "Reusable command presets"},
        {"name": "mass-runs", "description": "Batch simulation runs from CSV parameter sets"},
    ],
)

install_request_logging(app)
instrument_fastapi(app)

_logger = logging.getLogger(__name__)


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


def _case_root(extract_dir: Path) -> Path:
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


def _read_dict_value_from_text(text: str, dict_key: str) -> str | None:
    """Return the value for *dict_key* from parsed OpenFOAM dictionary lines."""
    for item in _parse_case_dict_values(text):
        if item["key"] == dict_key:
            return str(item["value"])
    return None


def _read_result_field_values(case_dir: Path, result_fields: list[dict]) -> list[dict]:
    """Read configured result field values from an extracted job case directory."""
    of_root = _case_root(case_dir)
    out: list[dict] = []
    for field in result_fields:
        field_key = str(field.get("key") or "")
        parsed = _split_input_field_key(field_key)
        label = str(field.get("label") or field_key)
        field_type = str(field.get("type") or "text")
        if not parsed:
            out.append({
                "key": field_key,
                "label": label,
                "type": field_type,
                "value": "",
                "error": "invalid key (use file::key)",
            })
            continue
        rel_file, dict_key = parsed
        target = of_root / rel_file
        if not target.is_file():
            out.append({
                "key": field_key,
                "label": label,
                "type": field_type,
                "value": "",
                "error": "file not found",
            })
            continue
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            out.append({
                "key": field_key,
                "label": label,
                "type": field_type,
                "value": "",
                "error": str(exc),
            })
            continue
        value = _read_dict_value_from_text(text, dict_key)
        out.append({
            "key": field_key,
            "label": label,
            "type": field_type,
            "value": value if value is not None else "",
        })
    return out


def _split_input_field_key(field_key: str) -> tuple[str, str] | None:
    """Parse ``system/controlDict::endTime`` into (relative file path, dict key)."""
    if "::" not in field_key:
        return None
    file_part, dict_key = field_key.split("::", 1)
    if not file_part.strip() or not dict_key.strip():
        return None
    return file_part.strip(), dict_key.strip()


_OPENFOAM_UNQUOTED_VALUE = re.compile(
    r"^(?:uniform|nonuniform)\b",
    re.IGNORECASE,
)


def _openfoam_value_needs_quotes(new_value: str, dict_key: str, orig: str) -> bool:
    """Whether a patched OpenFOAM dict assignment should be wrapped in double quotes."""
    if _OPENFOAM_UNQUOTED_VALUE.match(new_value.strip()):
        return False
    if dict_key == "value" and _OPENFOAM_UNQUOTED_VALUE.match(orig.strip()):
        return False
    return orig.startswith('"') or not re.fullmatch(r"[A-Za-z0-9_.+-]+", new_value)


def _patch_case_dict_value(text: str, dict_key: str, new_value: str, field_type: str) -> tuple[str, bool]:
    """Replace the first assignment line for *dict_key* in an OpenFOAM dictionary file."""
    num_line = re.compile(
        rf"^(\s*{re.escape(dict_key)}\s+)"
        r"(-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)"
        r"(\s*;.*)$",
    )
    text_line = re.compile(
        rf'^(\s*{re.escape(dict_key)}\s+)"?([^";]+)"?(\s*;.*)$',
    )
    out: list[str] = []
    changed = False
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        suffix = line[len(body) :]
        if not changed:
            if field_type == "number":
                m = num_line.match(body)
            else:
                m = text_line.match(body)
            if m:
                if field_type == "number":
                    body = f"{m.group(1)}{new_value}{m.group(3)}"
                else:
                    orig = m.group(2)
                    quoted = _openfoam_value_needs_quotes(new_value, dict_key, orig)
                    val = f'"{new_value}"' if quoted else new_value
                    body = f"{m.group(1)}{val}{m.group(3)}"
                changed = True
        out.append(body + suffix)
    return "".join(out), changed


def _apply_input_overrides(
    case_dir: Path,
    input_fields: list[dict],
    overrides: dict[str, str],
) -> int:
    """Write user input values into extracted case dictionary files. Returns fields applied."""
    of_root = _case_root(case_dir)
    applied = 0
    for field in input_fields:
        field_key = str(field.get("key") or "")
        parsed = _split_input_field_key(field_key)
        if not parsed:
            if field_key:
                _logger.warning(
                    "input field %r is not file::key; cannot patch case (use e.g. system/controlDict::endTime)",
                    field_key,
                )
            continue
        rel_file, dict_key = parsed
        value = overrides.get(field_key)
        if value is None:
            value = field.get("default", "")
        value = str(value).strip()
        if not value:
            continue

        target = of_root / rel_file
        if not target.is_file():
            _logger.warning("case file missing for input %s: %s", field_key, target)
            continue

        try:
            original = target.read_text(encoding="utf-8")
        except OSError as exc:
            _logger.warning("cannot read %s: %s", target, exc)
            continue

        field_type = str(field.get("type") or "text")
        patched, changed = _patch_case_dict_value(original, dict_key, value, field_type)
        if not changed:
            _logger.warning("no assignment for %s in %s", dict_key, rel_file)
            continue
        try:
            target.write_text(patched, encoding="utf-8")
        except OSError as exc:
            _logger.warning("cannot write %s: %s", target, exc)
            continue
        applied += 1
        _logger.info("applied input %s=%s -> %s", field_key, value, rel_file)
    return applied


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
        of_root = _case_root(case_dir)
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


def _parse_case_dict_values(text: str) -> list[dict]:
    """Extract simple key-value pairs from an case dictionary file."""
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


def _numeric_time_dirs(rel_names: list[str]) -> list[str]:
    """Sorted OpenFOAM time directory names (e.g. 0, 0.1, 100)."""
    dirs: set[str] = set()
    for n in rel_names:
        m = re.match(r"^([^/]+)/", n)
        if not m:
            continue
        top = m.group(1)
        if top == "0" or re.fullmatch(r"\d+(?:\.\d+)?", top):
            dirs.add(top)

    def sort_key(name: str) -> float:
        try:
            return float(name)
        except ValueError:
            return -1.0

    return sorted(dirs, key=sort_key)


def _analyze_case_zip(zip_bytes: bytes, *, include_latest_time: bool = False) -> dict:
    """Analyze a case ZIP and return structure + discovered variables."""
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

    if include_latest_time:
        time_dirs = _numeric_time_dirs(rel_names)
        if time_dirs:
            latest = time_dirs[-1]
            if latest != "0":
                latest_files = [
                    n for n in rel_names if re.match(rf"^{re.escape(latest)}/[^/]+$", n)
                ]
                key_files.extend(latest_files)
        post_files = [n for n in rel_names if n.startswith("postProcessing/") and n.count("/") >= 2]
        key_files.extend(post_files[:20])

    discovered: list[dict] = []
    for fp in key_files:
        content = read(fp)
        if not content:
            continue
        vals = _parse_case_dict_values(content)
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
        result = await asyncio.to_thread(_analyze_case_zip, raw)
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="Invalid ZIP archive") from e
    return result


@app.post("/api/simulations/analyze-result-zip")
async def analyze_result_zip(case_zip: UploadFile = File(...)) -> dict:
    """Analyze a completed-case ZIP; includes latest time dir and postProcessing paths."""
    raw = await case_zip.read()
    try:
        result = await asyncio.to_thread(_analyze_case_zip, raw, include_latest_time=True)
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


@app.get("/api/simulations/{sim_id}/predictive-model")
async def get_predictive_model(sim_id: str) -> dict:
    """Training/testing mass-run assignments for a simulation predictive model."""
    sim_coll: AsyncIOMotorCollection = app.state.simulations
    if not await sim_coll.find_one({"_id": sim_id}, projection={"_id": 1}):
        raise HTTPException(status_code=404, detail="Simulation not found")
    pred_coll: AsyncIOMotorCollection = app.state.predictive_models
    doc = await pred_coll.find_one({"_id": sim_id})
    return predictive_model_to_api(doc, simulation_id=sim_id)


@app.put("/api/simulations/{sim_id}/predictive-model")
async def put_predictive_model(sim_id: str, body: PredictiveModelBody) -> dict:
    """Persist training/testing mass-run assignments for a simulation."""
    sim_coll: AsyncIOMotorCollection = app.state.simulations
    if not await sim_coll.find_one({"_id": sim_id}, projection={"_id": 1}):
        raise HTTPException(status_code=404, detail="Simulation not found")

    train = list(dict.fromkeys(body.training_mass_run_ids))
    test = list(dict.fromkeys(body.testing_mass_run_ids))
    overlap = set(train) & set(test)
    if overlap:
        raise HTTPException(
            status_code=400,
            detail="A mass run cannot be assigned to both training and testing sets",
        )

    all_ids = set(train) | set(test)
    if all_ids:
        mass_coll: AsyncIOMotorCollection = app.state.mass_runs
        count = await mass_coll.count_documents(
            {"simulation_id": sim_id, "_id": {"$in": list(all_ids)}},
        )
        if count != len(all_ids):
            raise HTTPException(
                status_code=400,
                detail="One or more mass run IDs are invalid for this simulation",
            )

    now = datetime.now(timezone.utc).isoformat()
    pred_coll: AsyncIOMotorCollection = app.state.predictive_models
    existing = await pred_coll.find_one({"_id": sim_id})
    doc = {
        "_id": sim_id,
        "simulation_id": sim_id,
        "training_mass_run_ids": train,
        "testing_mass_run_ids": test,
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
    }
    await pred_coll.replace_one({"_id": sim_id}, doc, upsert=True)
    return predictive_model_to_api(doc, simulation_id=sim_id)


@app.post("/api/simulations")
async def create_simulation(
    title: str = Form(...),
    description: str = Form(""),
    commands: str = Form(""),
    input_fields_json: str = Form("[]"),
    result_fields_json: str = Form("[]"),
    case_zip: UploadFile = File(...),
    result_zip: UploadFile | None = File(None),
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

    try:
        result_fields = _json.loads(result_fields_json)
        if not isinstance(result_fields, list):
            result_fields = []
    except _json.JSONDecodeError:
        result_fields = []

    result_zip_path = ""
    if result_zip and result_zip.filename:
        result_bytes = await result_zip.read()
        try:
            zipfile.ZipFile(io.BytesIO(result_bytes))
        except zipfile.BadZipFile as e:
            raise HTTPException(status_code=400, detail="Invalid result ZIP archive") from e
        result_zip_path = str(sim_dir / "result.zip")
        await asyncio.to_thread(Path(result_zip_path).write_bytes, result_bytes)

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
        result_fields=result_fields,
        result_zip_path=result_zip_path,
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
    result_fields_json: str | None = Form(None),
    thumbnail: UploadFile | None = File(None),
    case_zip: UploadFile | None = File(None),
    result_zip: UploadFile | None = File(None),
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

    if result_fields_json is not None:
        try:
            result_fields = _json.loads(result_fields_json)
            if isinstance(result_fields, list):
                updates["result_fields"] = result_fields
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

    if result_zip and result_zip.filename:
        result_bytes = await result_zip.read()
        try:
            zipfile.ZipFile(io.BytesIO(result_bytes))
        except zipfile.BadZipFile as e:
            raise HTTPException(status_code=400, detail="Invalid result ZIP archive") from e
        sim_dir = TEMPLATES_DIR / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)
        result_path = sim_dir / "result.zip"
        await asyncio.to_thread(result_path.write_bytes, result_bytes)
        updates["result_zip_path"] = str(result_path)

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
        return await asyncio.to_thread(_analyze_case_zip, raw)
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="Invalid stored ZIP archive") from e


@app.get("/api/simulations/{sim_id}/result-case-analysis")
async def analyze_simulation_stored_result_case(sim_id: str) -> dict:
    """Return analyze-result-zip shape for the template's stored result.zip."""
    coll: AsyncIOMotorCollection = app.state.simulations
    doc = await coll.find_one({"_id": sim_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Simulation not found")
    zip_path = Path(doc.get("result_zip_path") or "")
    if not zip_path.is_file():
        raise HTTPException(status_code=404, detail="Result case ZIP not found")
    raw = await asyncio.to_thread(zip_path.read_bytes)
    try:
        return await asyncio.to_thread(_analyze_case_zip, raw, include_latest_time=True)
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="Invalid stored result ZIP archive") from e


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


def _resolved_simulation_commands(doc: dict) -> str:
    resolved_commands = (doc.get("commands") or "").strip()
    if resolved_commands and not re.search(r"(?<![\w/])foamToVTK(?!\w)", resolved_commands, re.IGNORECASE):
        resolved_commands = f"{resolved_commands} && foamToVTK"
    return resolved_commands


async def _create_job_from_simulation(
    sim_doc: dict,
    sim_id: str,
    overrides: dict[str, str],
    jobs_coll: AsyncIOMotorCollection,
    *,
    run_label: str | None = None,
) -> tuple[str, str, int]:
    """Extract template case, apply overrides, insert job row. Returns (job_id, commands, fields_applied)."""
    zip_path = Path(sim_doc["case_zip_path"])
    if not zip_path.is_file():
        raise HTTPException(status_code=500, detail="Template case ZIP missing from storage")

    job_id = str(uuid.uuid4())
    job_dir = JOBS_ROOT / job_id
    case_dir = job_dir / "case"
    case_dir.mkdir(parents=True, exist_ok=True)

    raw = await asyncio.to_thread(zip_path.read_bytes)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(case_dir)
    await asyncio.to_thread(_ensure_case_foam_marker, case_dir)

    input_fields = sim_doc.get("input_fields") or []
    applied = await asyncio.to_thread(
        _apply_input_overrides,
        case_dir,
        input_fields,
        overrides,
    )

    resolved_commands = _resolved_simulation_commands(sim_doc)
    now = _utc_now()
    await jobs_coll.insert_one(
        job_doc(
            job_id,
            status="pending",
            commands=resolved_commands,
            created_at=now,
            updated_at=now,
            run_instruction_id=None,
            run_instruction_name=run_label or sim_doc.get("title"),
            simulation_id=sim_id,
        )
    )
    return job_id, resolved_commands, applied


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

    overrides: dict = (body or {}).get("inputs", {}) if body else {}
    jobs_coll: AsyncIOMotorCollection = app.state.jobs
    job_id, resolved_commands, applied = await _create_job_from_simulation(
        doc, sim_id, overrides, jobs_coll
    )

    background_tasks.add_task(_run_job, job_id, resolved_commands)
    _logger.info(
        "job created job_id=%s simulation_id=%s inputs_applied=%d overrides=%d",
        job_id,
        sim_id,
        applied,
        len(overrides),
    )
    return {"id": job_id, "status": "pending", "simulation_id": sim_id}


@app.post("/api/simulations/{sim_id}/mass-run/preview")
async def preview_mass_run(
    sim_id: str,
    csv_file: UploadFile = File(...),
) -> dict:
    """Parse a mass-run CSV and return run count plus label/value preview per row."""
    coll: AsyncIOMotorCollection = app.state.simulations
    doc = await coll.find_one({"_id": sim_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if not csv_file.filename:
        raise HTTPException(status_code=400, detail="Missing CSV file")

    raw = await csv_file.read()
    runs, errors = parse_mass_run_csv(raw, doc.get("input_fields") or [])
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    labels: list[str] = []
    seen: set[str] = set()
    for run in runs:
        for inp in run.get("inputs") or []:
            lab = str(inp.get("label") or "")
            if lab and lab not in seen:
                seen.add(lab)
                labels.append(lab)

    preview_runs = [
        {
            "index": r["index"],
            "inputs": r["inputs"],
        }
        for r in runs
    ]
    return {
        "simulation_id": sim_id,
        "simulation_title": doc.get("title") or "",
        "total_runs": len(runs),
        "field_labels": labels,
        "runs": preview_runs,
    }


@app.post("/api/simulations/{sim_id}/mass-run")
async def start_mass_run(
    sim_id: str,
    background_tasks: BackgroundTasks,
    body: MassRunStartBody,
) -> dict:
    """Start batch execution of simulation runs (bounded concurrency via batch_size)."""
    coll: AsyncIOMotorCollection = app.state.simulations
    doc = await coll.find_one({"_id": sim_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Simulation not found")

    runs_in: list[dict] = body.runs
    if not runs_in:
        raise HTTPException(status_code=400, detail="runs must not be empty")

    input_fields = doc.get("input_fields") or []
    label_map_runs: list[dict] = []
    for i, row in enumerate(runs_in):
        inputs = row.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            raise HTTPException(status_code=400, detail=f"Run {i}: missing inputs")
        pairs: list[dict[str, str]] = []
        for inp in inputs:
            if not isinstance(inp, dict):
                continue
            label = str(inp.get("label") or "").strip()
            value = str(inp.get("value") if inp.get("value") is not None else "")
            if not label:
                continue
            pairs.append({"label": label, "value": value})
        if row.get("overrides") and isinstance(row["overrides"], dict):
            overrides = {str(k): str(v) for k, v in row["overrides"].items()}
        else:
            overrides, map_errors = inputs_to_overrides(pairs, input_fields)
            if map_errors:
                raise HTTPException(status_code=400, detail=f"Run {i}: {'; '.join(map_errors)}")
        label_map_runs.append(
            {
                "index": int(row.get("index", i)),
                "inputs": pairs,
                "overrides": overrides,
                "job_id": None,
                "status": "pending",
                "returncode": None,
                "error_message": None,
            }
        )

    mass_run_id = str(uuid.uuid4())
    now = _utc_now()
    mass_coll: AsyncIOMotorCollection = app.state.mass_runs
    await mass_coll.insert_one(
        mass_run_doc(
            mass_run_id,
            simulation_id=sim_id,
            simulation_title=doc.get("title") or "",
            batch_size=body.batch_size,
            total_runs=len(label_map_runs),
            runs=label_map_runs,
            status="pending",
            created_at=now,
            updated_at=now,
        )
    )
    background_tasks.add_task(_execute_mass_run, mass_run_id, sim_id, body.batch_size)
    _logger.info(
        "mass run started mass_run_id=%s simulation_id=%s total=%d batch_size=%d",
        mass_run_id,
        sim_id,
        len(label_map_runs),
        body.batch_size,
    )
    return {"id": mass_run_id, "status": "pending", "total_runs": len(label_map_runs)}


async def _execute_mass_run(mass_run_id: str, sim_id: str, batch_size: int) -> None:
    mass_coll: AsyncIOMotorCollection = app.state.mass_runs
    jobs_coll: AsyncIOMotorCollection = app.state.jobs
    sim_coll: AsyncIOMotorCollection = app.state.simulations

    doc = await sim_coll.find_one({"_id": sim_id})
    if not doc:
        await mass_coll.update_one(
            {"_id": mass_run_id},
            {"$set": {"status": "failed", "updated_at": _utc_now()}},
        )
        return

    await mass_coll.update_one(
        {"_id": mass_run_id},
        {"$set": {"status": "running", "updated_at": _utc_now()}},
    )

    mass_doc = await mass_coll.find_one({"_id": mass_run_id})
    if not mass_doc:
        return

    runs: list[dict] = list(mass_doc.get("runs") or [])
    sem = asyncio.Semaphore(max(1, min(batch_size, 64)))

    async def _run_one(run_entry: dict) -> None:
        idx = int(run_entry.get("index", 0))
        overrides = run_entry.get("overrides") or {}
        if not isinstance(overrides, dict):
            overrides = {}

        async with sem:
            try:
                job_id, commands, _ = await _create_job_from_simulation(
                    doc,
                    sim_id,
                    {str(k): str(v) for k, v in overrides.items()},
                    jobs_coll,
                    run_label=f"{doc.get('title') or 'sim'} run {idx + 1}",
                )
                await mass_coll.update_one(
                    {"_id": mass_run_id, "runs.index": idx},
                    {
                        "$set": {
                            "runs.$.job_id": job_id,
                            "runs.$.status": "running",
                            "updated_at": _utc_now(),
                        }
                    },
                )
                await _run_job(job_id, commands)
                job_row = await jobs_coll.find_one({"_id": job_id})
                st = (job_row or {}).get("status") or "failed"
                rc = (job_row or {}).get("returncode")
                err = (job_row or {}).get("error_message")
                success = st == "completed" and rc == 0
                await mass_coll.update_one(
                    {"_id": mass_run_id, "runs.index": idx},
                    {
                        "$set": {
                            "runs.$.status": st,
                            "runs.$.returncode": rc,
                            "runs.$.error_message": err,
                            "updated_at": _utc_now(),
                        },
                        "$inc": {
                            "completed_runs": 1 if success else 0,
                            "failed_runs": 0 if success else 1,
                        },
                    },
                )
            except Exception as exc:  # noqa: BLE001
                _logger.error("mass run row failed mass_run_id=%s index=%s err=%s", mass_run_id, idx, exc)
                await mass_coll.update_one(
                    {"_id": mass_run_id, "runs.index": idx},
                    {
                        "$set": {
                            "runs.$.status": "failed",
                            "runs.$.error_message": str(exc),
                            "updated_at": _utc_now(),
                        },
                        "$inc": {"failed_runs": 1},
                    },
                )

    await asyncio.gather(*[_run_one(r) for r in runs])

    final_doc = await mass_coll.find_one({"_id": mass_run_id})
    final_runs = (final_doc or {}).get("runs") or []
    completed = sum(
        1 for r in final_runs if r.get("status") == "completed" and r.get("returncode") == 0
    )
    failed = len(final_runs) - completed
    final_status = "completed" if failed == 0 else "completed_with_failures"
    await mass_coll.update_one(
        {"_id": mass_run_id},
        {
            "$set": {
                "status": final_status,
                "completed_runs": completed,
                "failed_runs": failed,
                "updated_at": _utc_now(),
            }
        },
    )
    _logger.info(
        "mass run finished mass_run_id=%s completed=%d failed=%d",
        mass_run_id,
        completed,
        failed,
    )


def _mass_run_input_labels(runs: list[dict]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for run in runs:
        for inp in run.get("inputs") or []:
            lab = str(inp.get("label") or "").strip()
            if lab and lab not in seen:
                seen.add(lab)
                labels.append(lab)
    return labels


def _build_mass_run_results_csv(mass_doc: dict, sim_doc: dict | None) -> str:
    """Build CSV: run metadata + input columns + simulation result_fields values per job."""
    runs: list[dict] = list(mass_doc.get("runs") or [])
    result_fields: list[dict] = list((sim_doc or {}).get("result_fields") or [])
    input_labels = _mass_run_input_labels(runs)
    result_headers = [
        str(f.get("label") or f.get("key") or "").strip() or f"result_{i}"
        for i, f in enumerate(result_fields)
    ]

    headers = ["run_index", "job_id", "status", "returncode", "error_message"]
    headers.extend(input_labels)
    headers.extend(result_headers)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)

    for run in sorted(runs, key=lambda r: int(r.get("index", 0))):
        idx = int(run.get("index", 0))
        job_id = str(run.get("job_id") or "")
        status = str(run.get("status") or "")
        rc = run.get("returncode")
        rc_str = "" if rc is None else str(rc)
        err = str(run.get("error_message") or "")

        input_map: dict[str, str] = {}
        for inp in run.get("inputs") or []:
            lab = str(inp.get("label") or "").strip()
            if lab:
                input_map[lab] = str(inp.get("value") if inp.get("value") is not None else "")

        row: list[str] = [str(idx + 1), job_id, status, rc_str, err]
        row.extend(input_map.get(lab, "") for lab in input_labels)

        result_values: list[str] = [""] * len(result_fields)
        if job_id and status == "completed" and rc == 0 and result_fields:
            case_dir = JOBS_ROOT / job_id / "case"
            if case_dir.is_dir():
                fields = _read_result_field_values(case_dir, result_fields)
                by_key = {str(f.get("key") or ""): str(f.get("value") or "") for f in fields}
                result_values = [
                    by_key.get(str(f.get("key") or ""), "") for f in result_fields
                ]
        row.extend(result_values)
        writer.writerow(row)

    return buf.getvalue()


@app.get("/api/mass-runs")
async def list_mass_runs(
    simulation_id: str | None = None,
    limit: int = 100,
) -> dict:
    """List past mass simulation runs (newest first)."""
    coll: AsyncIOMotorCollection = app.state.mass_runs
    query: dict = {}
    if simulation_id:
        query["simulation_id"] = simulation_id
    cap = max(1, min(limit, 200))
    cursor = coll.find(query).sort("created_at", -1).limit(cap)
    rows = await cursor.to_list(length=cap)
    items = [mass_run_list_item_to_api(r) for r in rows]
    return {"mass_runs": [i for i in items if i]}


@app.get("/api/mass-runs/{mass_run_id}")
async def get_mass_run(mass_run_id: str) -> dict:
    coll: AsyncIOMotorCollection = app.state.mass_runs
    doc = await coll.find_one({"_id": mass_run_id})
    row = mass_run_to_api(doc)
    if not row:
        raise HTTPException(status_code=404, detail="Mass run not found")
    return row


@app.get("/api/mass-runs/{mass_run_id}/results.csv")
async def download_mass_run_results_csv(mass_run_id: str) -> Response:
    """Download CSV with per-run inputs and result field values from completed cases."""
    mass_coll: AsyncIOMotorCollection = app.state.mass_runs
    sim_coll: AsyncIOMotorCollection = app.state.simulations
    mass_doc = await mass_coll.find_one({"_id": mass_run_id})
    if not mass_doc:
        raise HTTPException(status_code=404, detail="Mass run not found")
    sim_doc = await sim_coll.find_one({"_id": mass_doc.get("simulation_id")})
    csv_text = await asyncio.to_thread(_build_mass_run_results_csv, mass_doc, sim_doc)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="mass-run-{mass_run_id}-results.csv"',
        },
    )


def _zip_mass_run_to_temp_path(mass_run_id: str, runs: list[dict]) -> str:
    fd, out_path = tempfile.mkstemp(prefix="massrun-", suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for run in runs:
                job_id = run.get("job_id")
                if not job_id:
                    continue
                root = (JOBS_ROOT / str(job_id)).resolve()
                if not root.is_dir():
                    continue
                case = root / "case"
                if case.is_dir():
                    _ensure_case_foam_marker(case)
                idx = int(run.get("index", 0))
                prefix = f"run_{idx + 1:04d}_{job_id}"
                for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                    dirp = Path(dirpath)
                    dirnames[:] = [d for d in dirnames if not d.startswith("processor")]
                    for name in sorted(filenames):
                        fp = dirp / name
                        if not fp.is_file():
                            continue
                        arc = Path(prefix) / fp.relative_to(root)
                        zf.write(fp, arcname=str(arc))
    except Exception:
        _unlink_quiet(out_path)
        raise
    return out_path


@app.get("/api/mass-runs/{mass_run_id}/download")
async def download_mass_run(mass_run_id: str) -> FileResponse:
    coll: AsyncIOMotorCollection = app.state.mass_runs
    doc = await coll.find_one({"_id": mass_run_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Mass run not found")
    runs = doc.get("runs") or []
    job_ids = [r.get("job_id") for r in runs if r.get("job_id")]
    if not job_ids:
        raise HTTPException(status_code=400, detail="No job results available to download")
    out_path = await asyncio.to_thread(_zip_mass_run_to_temp_path, mass_run_id, runs)
    return FileResponse(
        out_path,
        media_type="application/zip",
        filename=f"mass-run-{mass_run_id}.zip",
        background=BackgroundTask(_unlink_quiet, out_path),
    )


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
    _logger.info("job created job_id=%s", job_id)
    return {"id": job_id, "status": "pending"}


async def _run_job(job_id: str, commands: str) -> None:
    coll: AsyncIOMotorCollection = app.state.jobs
    now = _utc_now()
    await coll.update_one({"_id": job_id}, {"$set": {"status": "running", "updated_at": now}})
    _logger.info("job run start job_id=%s", job_id)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(86400.0)) as client:
            r = await client.post(
                f"{RUNNER_URL}/internal/run",
                json={"job_id": job_id, "commands": commands},
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code >= 400:
                err = data.get("detail", r.text[:2000])
                _logger.error(
                    "job run failed job_id=%s runner_status=%s detail=%s",
                    job_id,
                    r.status_code,
                    err,
                )
                await coll.update_one(
                    {"_id": job_id},
                    {"$set": {"status": "failed", "error_message": str(err), "updated_at": _utc_now()}},
                )
                return

            rc = data.get("returncode", -1)
            log_path = data.get("log_path")
            st = "completed" if rc == 0 else "failed"
            _logger.info("job run done job_id=%s status=%s returncode=%s", job_id, st, rc)
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
        _logger.error("job run failed job_id=%s error=%s", job_id, e)
        await coll.update_one(
            {"_id": job_id},
            {"$set": {"status": "failed", "error_message": str(e), "updated_at": _utc_now()}},
        )


@app.get("/api/jobs")
async def list_jobs(
    exclude_mass_children: bool = Query(
        default=True,
        description="When true, omit jobs that belong to a mass run (listed under /api/mass-runs).",
    ),
) -> dict:
    coll: AsyncIOMotorCollection = app.state.jobs
    query: dict[str, Any] = {}
    if exclude_mass_children:
        mass_coll: AsyncIOMotorCollection = app.state.mass_runs
        child_ids = await collect_mass_run_child_job_ids(mass_coll)
        if child_ids:
            query["_id"] = {"$nin": list(child_ids)}
    cursor = coll.find(query, projection={"_id": 0}).sort("created_at", -1).limit(200)
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
    log_path = JOBS_ROOT / job_id / "forge.log"
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

    log_path = JOBS_ROOT / job_id / "forge.log"
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
        # STORED: mostly-binary case data barely compresses; avoids zlib peaks on huge files.
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


@app.get("/api/jobs/{job_id}/result-fields")
async def get_job_result_fields(job_id: str) -> dict:
    """Read result field values from the job case using the parent simulation's result_fields."""
    jobs_coll: AsyncIOMotorCollection = app.state.jobs
    sims_coll: AsyncIOMotorCollection = app.state.simulations
    job = await jobs_coll.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    sim_id = job.get("simulation_id")
    if not sim_id:
        return {"fields": []}
    sim_doc = await sims_coll.find_one({"_id": sim_id})
    if not sim_doc:
        return {"fields": []}
    result_fields = sim_doc.get("result_fields") or []
    if not result_fields:
        return {"fields": []}
    case_dir = JOBS_ROOT / job_id / "case"
    if not case_dir.is_dir():
        return {"fields": []}
    fields = await asyncio.to_thread(_read_result_field_values, case_dir, result_fields)
    return {"fields": fields}


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
