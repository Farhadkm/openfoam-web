"""MongoDB access for PSS trained model metadata."""

from __future__ import annotations

import os
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://mongo:27017")
MONGODB_DB = os.environ.get("MONGODB_DB", "forge_web")


async def connect_mongo() -> AsyncIOMotorClient:
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[MONGODB_DB]
    coll = db["pss_trained_models"]
    await coll.create_index([("simulation_id", 1), ("created_at", -1)])
    return client


def pss_models_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return client[MONGODB_DB]["pss_trained_models"]


def predictive_config_collection(client: AsyncIOMotorClient) -> AsyncIOMotorCollection:
    return client[MONGODB_DB]["predictive_models"]


def trained_model_to_api(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    model_id = doc.get("id") or doc.get("_id")
    return {
        "id": model_id,
        "simulation_id": doc.get("simulation_id"),
        "technique": doc.get("technique"),
        "training_mass_run_ids": list(doc.get("training_mass_run_ids") or []),
        "testing_mass_run_ids": list(doc.get("testing_mass_run_ids") or []),
        "feature_columns": list(doc.get("feature_columns") or []),
        "target_keys": list(doc.get("target_keys") or []),
        "metrics": doc.get("metrics") or {},
        "n_train_rows": doc.get("n_train_rows", 0),
        "n_test_rows": doc.get("n_test_rows", 0),
        "created_at": doc.get("created_at"),
    }


def trained_model_to_summary(doc: dict[str, Any]) -> dict[str, Any]:
    out = trained_model_to_api(doc)
    assert out is not None
    metrics = out.get("metrics") or {}
    agg = metrics.get("aggregate") or {}
    out["summary_metrics"] = {
        "rmse": agg.get("rmse"),
        "mae": agg.get("mae"),
        "r2": agg.get("r2"),
    }
    return out
