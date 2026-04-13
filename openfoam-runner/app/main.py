"""Internal HTTP service: runs OpenFOAM jobs inside Docker containers.

The runner itself is a small Python service. For each job it starts a short-lived
OpenFOAM container (e.g. opencfd/openfoam-run) with the case directory mounted in.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import docker
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="OpenFOAM Runner", version="1.0.0")

JOBS_ROOT = Path(os.environ.get("JOBS_ROOT", "/jobs")).resolve()
OPENFOAM_IMAGE = os.environ.get("OPENFOAM_IMAGE", "opencfd/openfoam-run:2512")
OPENFOAM_BASHRC = os.environ.get("OPENFOAM_BASHRC", "/usr/lib/openfoam/openfoam2512/etc/bashrc")
JOBS_VOLUME_NAME = os.environ.get("JOBS_VOLUME_NAME", "openfoam-web-jobs-data")
JOBS_VOLUME_MOUNT = os.environ.get("JOBS_VOLUME_MOUNT", "/work")

def _docker_client() -> docker.DockerClient:
    try:
        return docker.from_env()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Docker client init failed: {exc}") from exc


def _safe_job_id(raw: str) -> str:
    if ".." in raw or "/" in raw or "\\" in raw:
        raise HTTPException(status_code=400, detail="invalid job_id")
    return raw


class RunRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=128)
    """Shell commands run inside the case directory after OpenFOAM env is sourced (e.g. blockMesh && simpleFoam)."""

    commands: str = Field(
        default="blockMesh && simpleFoam",
        min_length=1,
        max_length=8000,
    )


class RunResponse(BaseModel):
    job_id: str
    returncode: int
    log_path: str


def _stream_container_logs_to_file(container: docker.models.containers.Container, log_path: Path) -> None:
    """Append stdout/stderr to log_path while the container runs (enables live tail + WS on the API)."""
    log_path.write_bytes(b"")
    with log_path.open("ab") as logf:
        try:
            for chunk in container.logs(stream=True, follow=True, stdout=True, stderr=True):
                if chunk:
                    logf.write(chunk)
                    logf.flush()
        except Exception as exc:  # noqa: BLE001
            logf.write(f"\n(log stream error: {exc})\n".encode("utf-8", errors="replace"))
            logf.flush()


def _container_exit_code(container: docker.models.containers.Container) -> int:
    result = container.wait()
    return int(result.get("StatusCode", -1))


@app.get("/health")
def health() -> dict[str, str]:
    c = _docker_client()
    try:
        info = c.version()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Docker not reachable: {exc}") from exc
    return {
        "status": "ok",
        "docker_api_version": str(info.get("ApiVersion", "")),
        "openfoam_image": OPENFOAM_IMAGE,
        "openfoam_bashrc": OPENFOAM_BASHRC,
        "jobs_volume_name": JOBS_VOLUME_NAME,
        "jobs_volume_mount": JOBS_VOLUME_MOUNT,
    }


@app.post("/internal/run", response_model=RunResponse)
def run_case(req: RunRequest) -> RunResponse:
    _safe_job_id(req.job_id)
    # Normalize Windows CRLF in user-provided commands to avoid:
    #   bash: line 1: $'\r': command not found
    commands = req.commands.replace("\r\n", "\n").replace("\r", "\n").strip()

    case_dir = (JOBS_ROOT / req.job_id / "case").resolve()
    if not case_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Case directory missing: {case_dir}")

    log_path = JOBS_ROOT / req.job_id / "openfoam.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Run inside a short-lived OpenFOAM container.
    #
    # Important (macOS / Docker Desktop):
    # We cannot bind-mount /jobs/... paths because the Docker daemon needs HOST paths.
    # Instead we mount the named volume that backs /jobs into the OpenFOAM container.
    job_dir = (JOBS_ROOT / req.job_id).resolve()
    foam_run = job_dir / "foam_run"
    foam_run.mkdir(parents=True, exist_ok=True)

    case_in_volume = f"{JOBS_VOLUME_MOUNT}/{req.job_id}/case"
    # opencfd/openfoam-run images are already configured with OpenFOAM env vars
    # (via their entrypoint). Sourcing bashrc under `set -u` can fail due to
    # strict unbound-variable checks. We therefore rely on the image env and
    # *do not* source bashrc here.
    inner = f'set -euo pipefail; cd "{case_in_volume}"; {commands}'
    c = _docker_client()

    container = None
    try:
        container = c.containers.run(
            image=OPENFOAM_IMAGE,
            command=["bash", "-lc", inner],
            detach=True,
            # Do NOT auto-remove: we want reliable log retrieval first.
            remove=False,
            volumes={JOBS_VOLUME_NAME: {"bind": JOBS_VOLUME_MOUNT, "mode": "rw"}},
            environment={
                "FOAM_RUN": f"{JOBS_VOLUME_MOUNT}/{req.job_id}/foam_run",
                # OpenMPI refuses to run as root unless explicitly allowed.
                # Many OpenFOAM tutorial Allrun scripts use `runParallel`/`mpirun`.
                "OMPI_ALLOW_RUN_AS_ROOT": "1",
                "OMPI_ALLOW_RUN_AS_ROOT_CONFIRM": "1",
            },
            working_dir=case_in_volume,
        )
    except docker.errors.ImageNotFound:
        # Try pulling once, then retry.
        c.images.pull(OPENFOAM_IMAGE)
        container = c.containers.run(
            image=OPENFOAM_IMAGE,
            command=["bash", "-lc", inner],
            detach=True,
            remove=False,
            volumes={JOBS_VOLUME_NAME: {"bind": JOBS_VOLUME_MOUNT, "mode": "rw"}},
            environment={
                "FOAM_RUN": f"{JOBS_VOLUME_MOUNT}/{req.job_id}/foam_run",
                "OMPI_ALLOW_RUN_AS_ROOT": "1",
                "OMPI_ALLOW_RUN_AS_ROOT_CONFIRM": "1",
            },
            working_dir=case_in_volume,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to start OpenFOAM container: {exc}") from exc

    rc = -1
    try:
        # Stream to disk during the run so the backend can tail openfoam.log and the UI shows live progress.
        _stream_container_logs_to_file(container, log_path)
        rc = _container_exit_code(container)
    finally:
        # Best-effort cleanup
        try:
            if container is not None:
                container.remove(force=True)
        except Exception:
            pass

    return RunResponse(
        job_id=req.job_id,
        returncode=rc,
        log_path=str(log_path),
    )


@app.post("/internal/cleanup/{job_id}")
def cleanup(job_id: str) -> dict[str, str]:
    """Optional: remove job workspace on runner (backend may own retention)."""
    _safe_job_id(job_id)
    root = (JOBS_ROOT / job_id).resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    try:
        root.relative_to(JOBS_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid path") from exc
    shutil.rmtree(root, ignore_errors=True)
    return {"status": "removed", "job_id": job_id}
