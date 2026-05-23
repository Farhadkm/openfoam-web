"""Predictive Simulation Service (PSS) — train XGBoost models on mass-run data and predict results."""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pydantic import BaseModel, Field

from shared.request_logging import install_request_logging
from shared.telemetry import configure_telemetry, instrument_fastapi

configure_telemetry()

from services.pss.dataset import _feature_columns, load_dataset_from_mass_runs
from services.pss.mongo_store import (
    connect_mongo,
    predictive_config_collection,
    pss_models_collection,
    trained_model_to_api,
    trained_model_to_summary,
)
from services.pss.predict import predict as run_predict
from services.pss.train import train_xgboost

SIMULATION_SERVICE_URL = os.environ.get(
    "SIMULATION_SERVICE_URL", "http://simulation:8001"
).rstrip("/")
PSS_MODELS_ROOT = Path(os.environ.get("PSS_MODELS_ROOT", "/pss_models")).resolve()

SUPPORTED_TECHNIQUES = frozenset({"xgboost"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = await connect_mongo()
    app.state.mongo_client = client
    app.state.pss_models: AsyncIOMotorCollection = pss_models_collection(client)
    app.state.predictive_config: AsyncIOMotorCollection = predictive_config_collection(client)
    PSS_MODELS_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        yield
    finally:
        client.close()


class TrainBody(BaseModel):
    technique: Literal["xgboost"] = "xgboost"
    training_mass_run_ids: list[str] = Field(default_factory=list)
    testing_mass_run_ids: list[str] = Field(default_factory=list)


class PredictBody(BaseModel):
    inputs: dict[str, str] = Field(default_factory=dict)


app = FastAPI(
    title="Forge Predictive Simulation Service",
    version="1.0.0",
    lifespan=lifespan,
    description="Train ML models on mass-run datasets and predict simulation result fields.",
)

install_request_logging(app)
instrument_fastapi(app)


async def _fetch_simulation(client: httpx.AsyncClient, sim_id: str) -> dict:
    r = await client.get(f"{SIMULATION_SERVICE_URL}/api/simulations/{sim_id}")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Simulation not found")
    r.raise_for_status()
    return r.json()


async def _resolve_mass_run_ids(
    config_coll: AsyncIOMotorCollection,
    sim_id: str,
    body: TrainBody,
) -> tuple[list[str], list[str]]:
    train = list(dict.fromkeys(body.training_mass_run_ids))
    test = list(dict.fromkeys(body.testing_mass_run_ids))
    if not train and not test:
        doc = await config_coll.find_one({"_id": sim_id})
        if doc:
            train = list(doc.get("training_mass_run_ids") or [])
            test = list(doc.get("testing_mass_run_ids") or [])
    if not train:
        raise HTTPException(
            status_code=400,
            detail="No training mass runs; assign training set on predictive model page or pass training_mass_run_ids",
        )
    overlap = set(train) & set(test)
    if overlap:
        raise HTTPException(
            status_code=400,
            detail="A mass run cannot be in both training and testing sets",
        )
    return train, test


@app.get("/health")
async def health():
    return {"service": "pss", "status": "ok", "techniques": sorted(SUPPORTED_TECHNIQUES)}


@app.get("/api/simulations/{sim_id}/predictive-models")
async def list_predictive_models(sim_id: str) -> dict:
    coll: AsyncIOMotorCollection = app.state.pss_models
    cursor = coll.find({"simulation_id": sim_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    return {
        "simulation_id": sim_id,
        "models": [trained_model_to_summary(d) for d in docs],
    }


@app.post("/api/simulations/{sim_id}/predictive-models/train")
async def train_model(sim_id: str, body: TrainBody) -> dict:
    if body.technique not in SUPPORTED_TECHNIQUES:
        raise HTTPException(status_code=400, detail=f"Unsupported technique: {body.technique}")

    async with httpx.AsyncClient() as client:
        sim = await _fetch_simulation(client, sim_id)
        input_fields = list(sim.get("input_fields") or [])
        result_fields = list(sim.get("result_fields") or [])
        if not result_fields:
            raise HTTPException(
                status_code=400,
                detail="Simulation has no result_fields configured",
            )

        train_ids, test_ids = await _resolve_mass_run_ids(
            app.state.predictive_config, sim_id, body
        )

        train_df = await load_dataset_from_mass_runs(
            client,
            SIMULATION_SERVICE_URL,
            train_ids,
            input_fields=input_fields,
            result_fields=result_fields,
        )
        test_df = await load_dataset_from_mass_runs(
            client,
            SIMULATION_SERVICE_URL,
            test_ids,
            input_fields=input_fields,
            result_fields=result_fields,
        ) if test_ids else train_df.iloc[0:0]

        feature_labels = _feature_columns(input_fields)
        model_id = str(uuid.uuid4())
        artifact_dir = PSS_MODELS_ROOT / model_id

        try:
            metrics, _ = train_xgboost(
                train_df,
                test_df,
                feature_labels=feature_labels,
                result_fields=result_fields,
                artifact_dir=artifact_dir,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "_id": model_id,
            "id": model_id,
            "simulation_id": sim_id,
            "technique": body.technique,
            "training_mass_run_ids": train_ids,
            "testing_mass_run_ids": test_ids,
            "feature_columns": feature_labels,
            "target_keys": [str(f.get("key") or "") for f in result_fields if f.get("key")],
            "metrics": metrics,
            "n_train_rows": int(len(train_df)),
            "n_test_rows": int(len(test_df)),
            "artifact_path": str(artifact_dir),
            "created_at": now,
        }
        coll: AsyncIOMotorCollection = app.state.pss_models
        await coll.insert_one(doc)
        out = trained_model_to_api(doc)
        assert out is not None
        return out


@app.get("/api/predictive-models/{model_id}")
async def get_predictive_model(model_id: str) -> dict:
    coll: AsyncIOMotorCollection = app.state.pss_models
    doc = await coll.find_one({"_id": model_id})
    out = trained_model_to_api(doc)
    if not out:
        raise HTTPException(status_code=404, detail="Model not found")
    return out


@app.post("/api/predictive-models/{model_id}/predict")
async def predict_results(model_id: str, body: PredictBody) -> dict:
    coll: AsyncIOMotorCollection = app.state.pss_models
    doc = await coll.find_one({"_id": model_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Model not found")

    sim_id = doc.get("simulation_id")
    artifact_dir = Path(str(doc.get("artifact_path") or PSS_MODELS_ROOT / model_id))

    async with httpx.AsyncClient() as client:
        sim = await _fetch_simulation(client, str(sim_id))
        input_fields = list(sim.get("input_fields") or [])
        result_fields = list(sim.get("result_fields") or [])

    try:
        values = run_predict(
            artifact_dir,
            input_fields=input_fields,
            overrides=body.inputs,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    fields = []
    for rf in result_fields:
        key = str(rf.get("key") or "")
        fields.append({
            "key": key,
            "label": str(rf.get("label") or key),
            "type": str(rf.get("type") or "text"),
            "value": values.get(key, ""),
        })

    return {
        "model_id": model_id,
        "simulation_id": sim_id,
        "predicted": True,
        "fields": fields,
        "values": values,
    }
