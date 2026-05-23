"""OpenAPI additions for CCS (WebSocket routes are not emitted by FastAPI)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

_WS_PATH: dict[str, dict[str, Any]] = {
    "/ws": {
        "get": {
            "tags": ["ai"],
            "summary": "AI chat (WebSocket)",
            "description": (
                "Streaming chat over WebSocket. Client sends JSON messages: "
                "`init`, `user_message`, `update_context`. "
                "Connect with `ws://` or `wss://` (BFF proxy: `/api/ai/ws`)."
            ),
            "responses": {
                "101": {"description": "Switching Protocols (WebSocket upgrade)"},
            },
        },
    },
}


def install_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        paths = schema.setdefault("paths", {})
        for path, ops in _WS_PATH.items():
            paths[path] = ops
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
