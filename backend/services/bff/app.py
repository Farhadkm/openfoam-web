"""Backend-for-Frontend (BFF) — browser-facing API gateway for Forge."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from pathlib import Path

from shared.request_logging import install_request_logging
from shared.telemetry import configure_telemetry, instrument_fastapi

configure_telemetry()

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from services.bff.openapi import install_openapi
from services.bff.proxy import (
    close_http_client,
    fetch_ccs_health,
    fetch_pss_health,
    fetch_simulation_health,
    proxy_http_ccs,
    proxy_http_pss,
    proxy_http_simulation,
    proxy_http_trame,
    proxy_websocket_ccs,
    proxy_websocket_simulation,
    proxy_websocket_trame,
)

_DEFAULT_CORS = "http://localhost:3000,http://127.0.0.1:3000"
CORS_ORIGINS = [
    o.strip()
    for o in (os.environ.get("CORS_ORIGINS") or _DEFAULT_CORS).split(",")
    if o.strip()
]

_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
_SCHEMA_OFF = {"include_in_schema": False}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        await close_http_client()


app = FastAPI(
    title="Forge BFF",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "Public API for the Next.js frontend. Proxies job/simulation traffic to the "
        "simulation service, conversation/AI traffic to CCS, and the VTK viewer to "
        "trame-viewer. Schemas here are stubs; see upstream OpenAPI links in `GET /health`."
    ),
    openapi_tags=[
        {"name": "health", "description": "BFF gateway health and downstream probes"},
        {"name": "jobs", "description": "Proxied to simulation service"},
        {"name": "simulations", "description": "Proxied to simulation service"},
        {"name": "run-instructions", "description": "Proxied to simulation service"},
        {"name": "conversations", "description": "Proxied to CCS (Chat Conversation Service)"},
        {"name": "ai", "description": "Proxied to CCS — WebSocket chat and thumbnails"},
        {"name": "viewer", "description": "Proxied to trame-viewer — VTK iframe and wslink"},
    ],
)

install_request_logging(app)
instrument_fastapi(app)
install_openapi(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    tags=["health"],
    summary="BFF health",
    description="BFF status and downstream simulation/CCS health. Lists links to other services' docs.",
)
async def health():
    simulation = await fetch_simulation_health()
    ccs = await fetch_ccs_health()
    pss = await fetch_pss_health()
    ok = (
        simulation.get("status") == "ok"
        and ccs.get("status") == "ok"
        and pss.get("status") == "ok"
    )
    return {
        "service": "bff",
        "status": "ok" if ok else "degraded",
        "downstream": {
            "simulation": simulation,
            "ccs": ccs,
            "pss": pss,
        },
        "swagger": {
            "bff": "/docs",
            "all_apis_scalar": "/api-docs/",
            "simulation": "docker compose exec simulation curl -s http://localhost:8001/docs",
            "ccs": "http://localhost:8081/docs",
            "runner": "docker compose exec forge-runner curl -s http://localhost:8080/docs",
            "ics": "docker compose exec ics curl -s http://localhost:8082/docs",
        },
    }


# ── Simulation proxies ──────────────────────────────────────────────────────


@app.api_route("/api/jobs", methods=_PROXY_METHODS, **_SCHEMA_OFF)
@app.api_route("/api/jobs/{rest:path}", methods=_PROXY_METHODS, **_SCHEMA_OFF)
async def proxy_jobs(request: Request, rest: str = ""):
    path = "api/jobs" + (f"/{rest}" if rest else "")
    return await proxy_http_simulation(request, path)


@app.websocket("/api/jobs/{job_id}/ws")
async def job_log_ws(websocket: WebSocket, job_id: str):
    await proxy_websocket_simulation(websocket, f"/api/jobs/{job_id}/ws")


@app.api_route("/api/predictive-models", methods=_PROXY_METHODS, **_SCHEMA_OFF)
@app.api_route("/api/predictive-models/{rest:path}", methods=_PROXY_METHODS, **_SCHEMA_OFF)
async def proxy_predictive_models(request: Request, rest: str = ""):
    path = "api/predictive-models" + (f"/{rest}" if rest else "")
    return await proxy_http_pss(request, path)


@app.api_route(
    "/api/simulations/{sim_id}/predictive-models",
    methods=_PROXY_METHODS,
    **_SCHEMA_OFF,
)
@app.api_route(
    "/api/simulations/{sim_id}/predictive-models/{rest:path}",
    methods=_PROXY_METHODS,
    **_SCHEMA_OFF,
)
async def proxy_simulation_predictive_models(
    request: Request,
    sim_id: str,
    rest: str = "",
):
    path = f"api/simulations/{sim_id}/predictive-models"
    if rest:
        path = f"{path}/{rest}"
    return await proxy_http_pss(request, path)


@app.api_route("/api/simulations", methods=_PROXY_METHODS, **_SCHEMA_OFF)
@app.api_route("/api/simulations/{rest:path}", methods=_PROXY_METHODS, **_SCHEMA_OFF)
async def proxy_simulations(request: Request, rest: str = ""):
    path = "api/simulations" + (f"/{rest}" if rest else "")
    return await proxy_http_simulation(request, path)


@app.api_route("/api/mass-runs", methods=_PROXY_METHODS, **_SCHEMA_OFF)
@app.api_route("/api/mass-runs/{rest:path}", methods=_PROXY_METHODS, **_SCHEMA_OFF)
async def proxy_mass_runs(request: Request, rest: str = ""):
    path = "api/mass-runs" + (f"/{rest}" if rest else "")
    return await proxy_http_simulation(request, path)


@app.api_route("/api/run-instructions", methods=_PROXY_METHODS, **_SCHEMA_OFF)
@app.api_route(
    "/api/run-instructions/{rest:path}",
    methods=_PROXY_METHODS,
    **_SCHEMA_OFF,
)
async def proxy_run_instructions(request: Request, rest: str = ""):
    path = "api/run-instructions" + (f"/{rest}" if rest else "")
    return await proxy_http_simulation(request, path)


# ── CCS proxies (conversations + AI) ────────────────────────────────────────


@app.api_route("/api/conversations", methods=_PROXY_METHODS, **_SCHEMA_OFF)
@app.api_route(
    "/api/conversations/{rest:path}",
    methods=_PROXY_METHODS,
    **_SCHEMA_OFF,
)
async def proxy_conversations(request: Request, rest: str = ""):
    path = "api/conversations" + (f"/{rest}" if rest else "")
    return await proxy_http_ccs(request, path)


@app.websocket("/api/ai/ws")
async def ai_chat_ws(websocket: WebSocket):
    await proxy_websocket_ccs(websocket, "/ws")


@app.api_route("/api/ai/generate-thumbnail", methods=["POST"], **_SCHEMA_OFF)
async def proxy_ai_thumbnail(request: Request):
    return await proxy_http_ccs(request, "generate-thumbnail")


@app.api_route("/api/ai/troubleshoot", methods=["POST"], **_SCHEMA_OFF)
async def proxy_ai_troubleshoot(request: Request):
    return await proxy_http_ccs(request, "api/ai/troubleshoot")


# ── Trame viewer (VTK iframe + wslink) ───────────────────────────────────────


@app.api_route("/viewer", methods=_PROXY_METHODS, **_SCHEMA_OFF)
@app.api_route("/viewer/{rest:path}", methods=_PROXY_METHODS, **_SCHEMA_OFF)
async def proxy_viewer(request: Request, rest: str = ""):
    return await proxy_http_trame(request, rest)


# Trame registers these at the viewer root; absolute "/forge-*.js" in the iframe
# resolves against the BFF origin (not /viewer) when embedded via /viewer.
@app.api_route("/forge-bridge.js", methods=["GET"], **_SCHEMA_OFF)
async def proxy_forge_bridge_js(request: Request):
    return await proxy_http_trame(request, "forge-bridge.js")


@app.api_route("/forge-fullbleed.js", methods=["GET"], **_SCHEMA_OFF)
async def proxy_forge_fullbleed_js(request: Request):
    return await proxy_http_trame(request, "forge-fullbleed.js")


@app.websocket("/viewer/ws")
async def viewer_ws(websocket: WebSocket):
    await proxy_websocket_trame(websocket, "/ws")


# ── Unified API docs (Scalar) ─────────────────────────────────────────────────

_API_DOCS_DIR = Path(__file__).resolve().parent / "static" / "api-docs"
if _API_DOCS_DIR.is_dir():

    @app.get("/api-docs", include_in_schema=False)
    async def api_docs_redirect():
        return RedirectResponse(url="/api-docs/", status_code=307)

    app.mount(
        "/api-docs",
        StaticFiles(directory=_API_DOCS_DIR, html=True),
        name="api-docs",
    )
