"""Async MongoDB access for jobs, simulations, and run instructions."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase


def _db(client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
    db_name = os.environ.get("MONGODB_DB", "forge_web")
    return client[db_name]


def _jobs_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _db(client)["jobs"]


def _run_instructions_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _db(client)["run_instructions"]


def _simulations_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _db(client)["simulations"]


async def connect_mongo() -> AsyncIOMotorClient:
    uri = os.environ.get("MONGODB_URI", "mongodb://mongo:27017").strip()
    if not uri:
        raise RuntimeError("MONGODB_URI is not set")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=10_000)
    await client.admin.command("ping")
    await _jobs_collection(client).create_index([("created_at", -1)])
    await _run_instructions_collection(client).create_index([("created_at", -1)])
    await _run_instructions_collection(client).create_index([("name", 1)])
    await _simulations_collection(client).create_index([("created_at", -1)])
    await _simulations_collection(client).create_index([("title", 1)])
    await _mass_runs_collection(client).create_index([("created_at", -1)])
    await _mass_runs_collection(client).create_index([("simulation_id", 1)])
    await _predictive_models_collection(client).create_index([("simulation_id", 1)], unique=True)
    return client


def jobs_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _jobs_collection(client)


def run_instructions_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _run_instructions_collection(client)


def simulations_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _simulations_collection(client)


def _mass_runs_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _db(client)["mass_runs"]


def mass_runs_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _mass_runs_collection(client)


def _predictive_models_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _db(client)["predictive_models"]


def predictive_models_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _predictive_models_collection(client)


def job_doc(
    job_id: str,
    *,
    status: str,
    commands: str,
    returncode: int | None = None,
    runner_log_path: str | None = None,
    error_message: str | None = None,
    created_at: str,
    updated_at: str,
    run_instruction_id: str | None = None,
    run_instruction_name: str | None = None,
    simulation_id: str | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "_id": job_id,
        "id": job_id,
        "status": status,
        "commands": commands,
        "returncode": returncode,
        "runner_log_path": runner_log_path,
        "error_message": error_message,
        "created_at": created_at,
        "updated_at": updated_at,
    }
    if run_instruction_id:
        d["run_instruction_id"] = run_instruction_id
    if run_instruction_name:
        d["run_instruction_name"] = run_instruction_name
    if simulation_id:
        d["simulation_id"] = simulation_id
    return d


def row_to_api(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    out: dict[str, Any] = {
        "id": doc.get("id") or doc.get("_id"),
        "status": doc["status"],
        "commands": doc["commands"],
        "returncode": doc.get("returncode"),
        "error_message": doc.get("error_message"),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
        "runner_log_path": doc.get("runner_log_path"),
    }
    if doc.get("run_instruction_id"):
        out["run_instruction_id"] = doc["run_instruction_id"]
    if doc.get("run_instruction_name"):
        out["run_instruction_name"] = doc["run_instruction_name"]
    if doc.get("simulation_id"):
        out["simulation_id"] = doc["simulation_id"]
    return out


def instruction_doc(
    instruction_id: str,
    *,
    name: str,
    commands: str,
    description: str,
    created_at: str,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "_id": instruction_id,
        "id": instruction_id,
        "name": name,
        "commands": commands,
        "description": description,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def instruction_to_api(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    return {
        "id": doc.get("id") or doc.get("_id"),
        "name": doc["name"],
        "commands": doc["commands"],
        "description": doc.get("description") or "",
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }


def simulation_doc(
    sim_id: str,
    *,
    title: str,
    description: str,
    commands: str,
    case_zip_path: str,
    thumbnail_path: str,
    input_fields: list[dict[str, Any]],
    result_fields: list[dict[str, Any]] | None = None,
    result_zip_path: str = "",
    created_at: str,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "_id": sim_id,
        "id": sim_id,
        "title": title,
        "description": description,
        "commands": commands,
        "case_zip_path": case_zip_path,
        "thumbnail_path": thumbnail_path,
        "input_fields": input_fields,
        "result_fields": result_fields or [],
        "result_zip_path": result_zip_path,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def simulation_to_api(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    sim_id = doc.get("id") or doc.get("_id")
    return {
        "id": sim_id,
        "title": doc["title"],
        "description": doc.get("description") or "",
        "commands": doc.get("commands") or "",
        "case_zip_path": doc.get("case_zip_path") or "",
        "thumbnail_url": f"/api/simulations/{sim_id}/thumbnail" if doc.get("thumbnail_path") else "",
        "input_fields": doc.get("input_fields") or [],
        "result_fields": doc.get("result_fields") or [],
        "has_result_zip": bool(doc.get("result_zip_path")),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }


def mass_run_doc(
    mass_run_id: str,
    *,
    simulation_id: str,
    simulation_title: str,
    batch_size: int,
    total_runs: int,
    runs: list[dict[str, Any]],
    status: str,
    created_at: str,
    updated_at: str,
    completed_runs: int = 0,
    failed_runs: int = 0,
) -> dict[str, Any]:
    return {
        "_id": mass_run_id,
        "id": mass_run_id,
        "simulation_id": simulation_id,
        "simulation_title": simulation_title,
        "batch_size": batch_size,
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "failed_runs": failed_runs,
        "runs": runs,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def mass_run_to_api(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    return {
        "id": doc.get("id") or doc.get("_id"),
        "simulation_id": doc["simulation_id"],
        "simulation_title": doc.get("simulation_title") or "",
        "batch_size": doc.get("batch_size", 1),
        "total_runs": doc.get("total_runs", 0),
        "completed_runs": doc.get("completed_runs", 0),
        "failed_runs": doc.get("failed_runs", 0),
        "runs": doc.get("runs") or [],
        "status": doc["status"],
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }


def mass_run_list_item_to_api(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Summary for mass-run list (no per-run rows)."""
    if not doc:
        return None
    return {
        "id": doc.get("id") or doc.get("_id"),
        "simulation_id": doc["simulation_id"],
        "simulation_title": doc.get("simulation_title") or "",
        "batch_size": doc.get("batch_size", 1),
        "total_runs": doc.get("total_runs", 0),
        "completed_runs": doc.get("completed_runs", 0),
        "failed_runs": doc.get("failed_runs", 0),
        "status": doc["status"],
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }


def mass_run_child_job_ids_from_docs(docs: Iterable[dict[str, Any]]) -> set[str]:
    """Job IDs referenced in mass_runs.runs (children of a mass run)."""
    ids: set[str] = set()
    for doc in docs:
        for run in doc.get("runs") or []:
            jid = run.get("job_id")
            if jid:
                ids.add(str(jid))
    return ids


async def collect_mass_run_child_job_ids(coll: AsyncIOMotorCollection) -> set[str]:
    cursor = coll.find({}, projection={"runs.job_id": 1})
    rows = await cursor.to_list(length=10_000)
    return mass_run_child_job_ids_from_docs(rows)


def predictive_model_to_api(doc: dict[str, Any] | None, *, simulation_id: str) -> dict[str, Any]:
    if not doc:
        return {
            "simulation_id": simulation_id,
            "training_mass_run_ids": [],
            "testing_mass_run_ids": [],
            "updated_at": None,
        }
    return {
        "simulation_id": doc.get("simulation_id") or simulation_id,
        "training_mass_run_ids": list(doc.get("training_mass_run_ids") or []),
        "testing_mass_run_ids": list(doc.get("testing_mass_run_ids") or []),
        "updated_at": doc.get("updated_at"),
    }
