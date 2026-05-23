"""HTTP and WebSocket reverse proxy to internal backend microservices."""

from __future__ import annotations

import asyncio
import logging
import os
import httpx
from fastapi import Request, Response, WebSocket, WebSocketDisconnect
from shared.http_body_logging import (
    _is_health_path,
    body_logging_enabled,
    preview_body,
    should_skip_path,
)
from starlette.datastructures import Headers

SIMULATION_SERVICE_URL = os.getenv(
    "SIMULATION_SERVICE_URL", "http://simulation:8001"
).rstrip("/")
CCS_SERVICE_URL = os.getenv("CCS_SERVICE_URL", "http://ccs:8081").rstrip("/")
TRAME_VIEWER_URL = os.getenv(
    "TRAME_VIEWER_URL", "http://trame-viewer:8090"
).rstrip("/")
PSS_SERVICE_URL = os.getenv("PSS_SERVICE_URL", "http://pss:8003").rstrip("/")

_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)

_CLIENT: httpx.AsyncClient | None = None
_logger = logging.getLogger(__name__)


def _http_to_ws_url(base: str) -> str:
    return base.replace("https://", "wss://").replace("http://", "ws://")


def _forward_headers(headers: Headers) -> dict[str, str]:
    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in _HOP_BY_HOP
    }


async def _http_client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(86400.0, connect=30.0),
            follow_redirects=False,
        )
    return _CLIENT


async def close_http_client() -> None:
    global _CLIENT
    if _CLIENT is not None:
        await _CLIENT.aclose()
        _CLIENT = None


async def proxy_http(
    request: Request,
    upstream_base: str,
    path: str,
    *,
    target: str,
) -> Response:
    base = upstream_base.rstrip("/")
    url = f"{base}/{path}" if path else f"{base}/"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    log_proxy = not (
        _is_health_path(request.url.path) or _is_health_path(path)
    )
    if log_proxy:
        _logger.info(
            "proxy %s %s -> %s/%s", request.method, request.url.path, target, path
        )

    body = await request.body()
    client = await _http_client()
    upstream = await client.request(
        request.method,
        url,
        headers=_forward_headers(request.headers),
        content=body if body else None,
    )

    if log_proxy:
        _logger.info(
            "proxy %s -> %s/%s status=%s",
            request.method,
            target,
            path,
            upstream.status_code,
        )

    if (
        log_proxy
        and body_logging_enabled()
        and not should_skip_path(request.url.path)
    ):
        preview = preview_body(
            upstream.content,
            upstream.headers.get("content-type"),
        )
        if preview:
            _logger.info(
                "proxy response %s %s -> %s status=%s body_preview=%s",
                request.method,
                request.url.path,
                target,
                upstream.status_code,
                preview,
            )

    response_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


async def proxy_http_simulation(request: Request, path: str) -> Response:
    return await proxy_http(request, SIMULATION_SERVICE_URL, path, target="simulation")


async def proxy_http_ccs(request: Request, path: str) -> Response:
    return await proxy_http(request, CCS_SERVICE_URL, path, target="ccs")


async def proxy_http_trame(request: Request, path: str) -> Response:
    return await proxy_http(request, TRAME_VIEWER_URL, path, target="trame-viewer")


async def proxy_http_pss(request: Request, path: str) -> Response:
    return await proxy_http(request, PSS_SERVICE_URL, path, target="pss")


async def proxy_websocket(
    client_ws: WebSocket,
    upstream_base: str,
    path: str,
) -> None:
    import websockets

    await client_ws.accept()
    ws_base = _http_to_ws_url(upstream_base.rstrip("/"))
    backend_url = f"{ws_base}{path}"
    if client_ws.url.query:
        backend_url = f"{backend_url}?{client_ws.url.query}"

    try:
        async with websockets.connect(
            backend_url,
            max_size=2**24,
            ping_interval=20,
            ping_timeout=120,
        ) as backend_ws:

            async def client_to_backend() -> None:
                try:
                    while True:
                        msg = await client_ws.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if "text" in msg and msg["text"] is not None:
                            await backend_ws.send(msg["text"])
                        elif "bytes" in msg and msg["bytes"] is not None:
                            await backend_ws.send(msg["bytes"])
                except WebSocketDisconnect:
                    pass

            async def backend_to_client() -> None:
                async for message in backend_ws:
                    if isinstance(message, str):
                        await client_ws.send_text(message)
                    else:
                        await client_ws.send_bytes(message)

            forward_client = asyncio.create_task(client_to_backend())
            forward_backend = asyncio.create_task(backend_to_client())
            done, pending = await asyncio.wait(
                {forward_client, forward_backend},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                _ = task.exception() if not task.cancelled() else None

    except Exception:
        pass
    finally:
        try:
            await client_ws.close()
        except Exception:
            pass


async def proxy_websocket_simulation(client_ws: WebSocket, path: str) -> None:
    await proxy_websocket(client_ws, SIMULATION_SERVICE_URL, path)


async def proxy_websocket_ccs(client_ws: WebSocket, path: str) -> None:
    await proxy_websocket(client_ws, CCS_SERVICE_URL, path)


async def proxy_websocket_trame(client_ws: WebSocket, path: str) -> None:
    await proxy_websocket(client_ws, TRAME_VIEWER_URL, path)


async def fetch_upstream_health(base_url: str, service_name: str) -> dict:
    try:
        client = await _http_client()
        r = await client.get(f"{base_url.rstrip('/')}/health", timeout=5.0)
        if r.status_code == 200:
            data = r.json()
            return {"status": "ok", **data}
        return {"status": "degraded", "http_status": r.status_code, "service": service_name}
    except Exception as exc:
        return {"status": "unavailable", "service": service_name, "error": str(exc)}


async def fetch_simulation_health() -> dict:
    return await fetch_upstream_health(SIMULATION_SERVICE_URL, "simulation")


async def fetch_ccs_health() -> dict:
    return await fetch_upstream_health(CCS_SERVICE_URL, "ccs")


async def fetch_pss_health() -> dict:
    return await fetch_upstream_health(PSS_SERVICE_URL, "pss")
