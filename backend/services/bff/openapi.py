"""OpenAPI stubs for BFF proxy routes (runtime handlers live in app.py)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

_PROXY_JSON = {
    "description": "Proxied response (status and body pass through from upstream).",
    "content": {
        "application/json": {"schema": {"type": "object", "additionalProperties": True}}
    },
}

_PROXY_BINARY = {
    "description": "Proxied binary response from upstream.",
    "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
}

_PROXY_HTML = {
    "description": "Proxied HTML/assets from trame-viewer.",
    "content": {"text/html": {"schema": {"type": "string"}}},
}


def _op(
    *,
    tag: str,
    summary: str,
    description: str,
    upstream: str,
    responses: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tags": [tag],
        "summary": summary,
        "description": f"{description}\n\n**Upstream:** `{upstream}`",
        "responses": responses
        or {
            "200": _PROXY_JSON,
            "404": {"description": "Not found (upstream)"},
            "502": {"description": "Upstream unavailable"},
        },
    }


def _ws_op(*, tag: str, summary: str, description: str, upstream: str) -> dict[str, Any]:
    return {
        "tags": [tag],
        "summary": summary,
        "description": (
            f"{description}\n\n**WebSocket** — connect with `ws://` or `wss://`. "
            f"**Upstream:** `{upstream}`"
        ),
        "responses": {
            "101": {"description": "Switching Protocols (WebSocket upgrade)"},
        },
    }


# Paths the Next.js client uses (frontend/lib/api.ts, aiChat.ts, trame.ts).
DOCUMENTED_PATHS: dict[str, dict[str, dict[str, Any]]] = {
    "/api/jobs": {
        "get": _op(
            tag="jobs",
            summary="List jobs",
            description="List CFD jobs.",
            upstream="GET simulation /api/jobs",
        ),
        "post": _op(
            tag="jobs",
            summary="Create job (upload case ZIP)",
            description="Multipart upload of a case archive.",
            upstream="POST simulation /api/jobs",
        ),
    },
    "/api/jobs/{job_id}": {
        "get": _op(
            tag="jobs",
            summary="Get job",
            description="Job metadata and status.",
            upstream="GET simulation /api/jobs/{job_id}",
        ),
    },
    "/api/jobs/{job_id}/log": {
        "get": _op(
            tag="jobs",
            summary="Get job log",
            description="Solver log text.",
            upstream="GET simulation /api/jobs/{job_id}/log",
        ),
    },
    "/api/jobs/{job_id}/outputs": {
        "get": _op(
            tag="jobs",
            summary="List job outputs",
            description="Time directories, regions, VTK/foam flags.",
            upstream="GET simulation /api/jobs/{job_id}/outputs",
        ),
    },
    "/api/jobs/{job_id}/download": {
        "get": _op(
            tag="jobs",
            summary="Download case archive",
            description="ZIP download of the job case directory.",
            upstream="GET simulation /api/jobs/{job_id}/download",
            responses={"200": _PROXY_BINARY},
        ),
    },
    "/api/jobs/{job_id}/case/{file_path}": {
        "get": _op(
            tag="jobs",
            summary="Read case file",
            description="Fetch a file under the job case tree.",
            upstream="GET simulation /api/jobs/{job_id}/case/{file_path}",
        ),
    },
    "/api/simulations": {
        "get": _op(
            tag="simulations",
            summary="List simulations",
            description="Simulation templates.",
            upstream="GET simulation /api/simulations",
        ),
        "post": _op(
            tag="simulations",
            summary="Create simulation",
            description="Create template (multipart).",
            upstream="POST simulation /api/simulations",
        ),
    },
    "/api/simulations/analyze-zip": {
        "post": _op(
            tag="simulations",
            summary="Analyze case ZIP",
            description="Inspect archive before creating a simulation.",
            upstream="POST simulation /api/simulations/analyze-zip",
        ),
    },
    "/api/simulations/{sim_id}": {
        "get": _op(
            tag="simulations",
            summary="Get simulation",
            description="Template metadata.",
            upstream="GET simulation /api/simulations/{sim_id}",
        ),
        "patch": _op(
            tag="simulations",
            summary="Update simulation",
            description="Update template fields.",
            upstream="PATCH simulation /api/simulations/{sim_id}",
        ),
        "delete": _op(
            tag="simulations",
            summary="Delete simulation",
            description="Remove template.",
            upstream="DELETE simulation /api/simulations/{sim_id}",
        ),
    },
    "/api/simulations/{sim_id}/run": {
        "post": _op(
            tag="simulations",
            summary="Run simulation",
            description="Start a job from this template.",
            upstream="POST simulation /api/simulations/{sim_id}/run",
        ),
    },
    "/api/simulations/{sim_id}/thumbnail": {
        "get": _op(
            tag="simulations",
            summary="Simulation thumbnail",
            description="PNG thumbnail image.",
            upstream="GET simulation /api/simulations/{sim_id}/thumbnail",
            responses={"200": _PROXY_BINARY},
        ),
    },
    "/api/simulations/{sim_id}/case-analysis": {
        "get": _op(
            tag="simulations",
            summary="Case analysis",
            description="Parsed case structure for the UI.",
            upstream="GET simulation /api/simulations/{sim_id}/case-analysis",
        ),
    },
    "/api/run-instructions": {
        "get": _op(
            tag="run-instructions",
            summary="List run instructions",
            description="Reusable command presets.",
            upstream="GET simulation /api/run-instructions",
        ),
        "post": _op(
            tag="run-instructions",
            summary="Create run instruction",
            description="Create a preset.",
            upstream="POST simulation /api/run-instructions",
        ),
    },
    "/api/run-instructions/{instruction_id}": {
        "get": _op(
            tag="run-instructions",
            summary="Get run instruction",
            description="Single preset.",
            upstream="GET simulation /api/run-instructions/{instruction_id}",
        ),
        "patch": _op(
            tag="run-instructions",
            summary="Update run instruction",
            description="Update preset fields.",
            upstream="PATCH simulation /api/run-instructions/{instruction_id}",
        ),
        "delete": _op(
            tag="run-instructions",
            summary="Delete run instruction",
            description="Remove preset.",
            upstream="DELETE simulation /api/run-instructions/{instruction_id}",
        ),
    },
    "/api/conversations": {
        "get": _op(
            tag="conversations",
            summary="List conversations",
            description="AI chat conversations.",
            upstream="GET ccs /api/conversations",
        ),
        "post": _op(
            tag="conversations",
            summary="Create conversation",
            description="Start a new conversation.",
            upstream="POST ccs /api/conversations",
        ),
    },
    "/api/conversations/{conversation_id}": {
        "get": _op(
            tag="conversations",
            summary="Get conversation",
            description="Conversation with messages.",
            upstream="GET ccs /api/conversations/{conversation_id}",
        ),
        "delete": _op(
            tag="conversations",
            summary="Delete conversation",
            description="Remove conversation.",
            upstream="DELETE ccs /api/conversations/{conversation_id}",
        ),
    },
    "/api/conversations/{conversation_id}/messages": {
        "get": _op(
            tag="conversations",
            summary="List messages",
            description="Message history for a conversation.",
            upstream="GET ccs /api/conversations/{conversation_id}/messages",
        ),
    },
    "/api/ai/generate-thumbnail": {
        "post": _op(
            tag="ai",
            summary="Generate thumbnail (AI)",
            description="PNG thumbnail via Vertex image model.",
            upstream="POST ccs /generate-thumbnail",
            responses={"200": _PROXY_BINARY},
        ),
    },
    "/api/ai/troubleshoot": {
        "post": _op(
            tag="ai",
            summary="Troubleshoot job log (AI)",
            description=(
                "One-shot OpenFOAM/Forge troubleshooting guide from job log and template context. "
                "Does not use ICS intent routing."
            ),
            upstream="POST ccs /api/ai/troubleshoot",
        ),
    },
    "/viewer": {
        "get": _op(
            tag="viewer",
            summary="Trame viewer (root)",
            description="VTK iframe entrypoint.",
            upstream="GET trame-viewer /",
            responses={"200": _PROXY_HTML},
        ),
    },
    "/viewer/{path}": {
        "get": _op(
            tag="viewer",
            summary="Trame viewer assets",
            description="Static assets and subpaths under the viewer app.",
            upstream="GET trame-viewer /{path}",
            responses={"200": _PROXY_HTML},
        ),
    },
}

WEBSOCKET_PATHS: dict[str, dict[str, dict[str, Any]]] = {
    "/api/jobs/{job_id}/ws": {
        "get": _ws_op(
            tag="jobs",
            summary="Job log stream (WebSocket)",
            description="Live tail of solver logs for a job.",
            upstream="WS simulation /api/jobs/{job_id}/ws",
        ),
    },
    "/api/ai/ws": {
        "get": _ws_op(
            tag="ai",
            summary="AI chat (WebSocket)",
            description="Streaming chat (`init`, `user_message`, `update_context`).",
            upstream="WS ccs /ws",
        ),
    },
    "/viewer/ws": {
        "get": _ws_op(
            tag="viewer",
            summary="Trame wslink (WebSocket)",
            description="VTK remote rendering session.",
            upstream="WS trame-viewer /ws",
        ),
    },
}

# Catch-all proxy patterns (hidden from default schema; listed for reference).
CATCH_ALL_PATHS = (
    "/api/jobs/{rest}",
    "/api/simulations/{rest}",
    "/api/run-instructions/{rest}",
    "/api/conversations/{rest}",
    "/viewer/{rest}",
)


def build_openapi(app: FastAPI) -> dict[str, Any]:
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    paths: dict[str, Any] = schema.setdefault("paths", {})

    for path, catch_all in list(paths.items()):
        if path in CATCH_ALL_PATHS:
            del paths[path]

    for path, ops in DOCUMENTED_PATHS.items():
        paths[path] = {**paths.get(path, {}), **ops}

    for path, ops in WEBSOCKET_PATHS.items():
        paths[path] = ops

    return schema


def install_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        app.openapi_schema = build_openapi(app)
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
