"""Async MongoDB access for job metadata."""

from __future__ import annotations

import os
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase


def _db(client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
    db_name = os.environ.get("MONGODB_DB", "openfoam_web")
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
    return client


def jobs_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _jobs_collection(client)


def run_instructions_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _run_instructions_collection(client)


def simulations_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return _simulations_collection(client)


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
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }
