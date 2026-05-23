"""Intent Classification Service (ICS) – classify user questions by intent."""

from __future__ import annotations

from shared.request_logging import install_request_logging
from shared.telemetry import configure_telemetry, instrument_fastapi

configure_telemetry()

import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.ics.classifier import classify_message
from services.ics.intents import INTENT_DEFINITIONS
from shared.vertex import MODEL_NAME, credentials_health

load_dotenv()

app = FastAPI(
    title="Intent Classification Service",
    version="1.0.0",
    description="Classifies chat messages by intent for CCS (internal; not proxied by BFF).",
    openapi_tags=[
        {"name": "health", "description": "Service health and intent catalog"},
        {"name": "classification", "description": "Intent classification"},
    ],
)

install_request_logging(app)
instrument_fastapi(app)

_logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ClassifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    page_context: str = Field(default="run", pattern="^(run|job)$")


@app.get("/health")
async def health():
    cred = credentials_health()
    return {
        "service": "ics",
        "status": "ok" if cred["ok"] else "degraded",
        "model": MODEL_NAME,
        "vertex_credentials": cred,
        "intents": INTENT_DEFINITIONS,
    }


@app.get("/intents")
async def list_intents():
    return {"intents": INTENT_DEFINITIONS}


@app.post("/classify")
async def classify(body: ClassifyRequest):
    from opentelemetry import trace

    from shared.conversation_tracing import enrich_current_span_from_baggage

    enrich_current_span_from_baggage()
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("forge.page.context", body.page_context)
        preview = body.message if len(body.message) <= 512 else body.message[:512] + "..."
        span.set_attribute("forge.user.message.preview", preview)

    result = await classify_message(body.message, body.page_context)
    if span.is_recording():
        primary = result.get("primary_intent")
        if primary:
            span.set_attribute("forge.intent.primary", str(primary))
    intents = result.get("intents") or []
    intent_ids = [
        i.get("intent") for i in intents if isinstance(i, dict) and i.get("intent")
    ]
    _logger.info(
        "classify page_context=%s intents=%s primary=%s",
        body.page_context,
        intent_ids,
        result.get("primary_intent"),
    )
    return result
