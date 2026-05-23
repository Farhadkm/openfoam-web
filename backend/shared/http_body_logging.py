"""HTTP response body preview logging (dev-oriented; truncate and redact secrets)."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

# Max bytes to buffer for preview/logging (larger responses are summarized only).
MAX_BODY_BYTES = 64 * 1024

_CREDENTIAL_PATH_MARKERS = (
    "password",
    "secret",
    "token",
    "credential",
    "api-key",
    "apikey",
)

_SECRET_JSON_RE = re.compile(
    r'("(?:password|secret|token|api[_-]?key|authorization|access_token|refresh_token)"'
    r'\s*:\s*)"[^"]*"',
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)


def _env_bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() not in ("false", "0", "no", "off")


def preview_max_chars() -> int:
    try:
        return max(0, int(os.getenv("LOG_HTTP_BODY_MAX", "1024")))
    except ValueError:
        return 1024


def body_logging_enabled() -> bool:
    if not _env_bool("LOG_HTTP_BODY_ENABLED", "true"):
        return False
    return preview_max_chars() > 0


def _is_health_path(path: str) -> bool:
    """True for health probe paths (logging suppressed; handlers still run)."""
    if not path:
        return False
    p = path.split("?", 1)[0]
    if not p.startswith("/"):
        p = f"/{p}"
    p = p.rstrip("/") or "/"
    if p == "/health":
        return True
    return p.endswith("/health")


def should_skip_path(path: str) -> bool:
    """Skip paths that may carry secrets, binary viewer assets, or health probes."""
    if _is_health_path(path):
        return True
    lower = path.lower()
    if lower.startswith("/viewer"):
        return True
    return any(marker in lower for marker in _CREDENTIAL_PATH_MARKERS)


def should_skip_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    ct = content_type.lower().split(";")[0].strip()
    if ct in ("multipart/form-data", "application/octet-stream"):
        return True
    if "zip" in ct:
        return True
    return False


def is_likely_binary(content_type: str | None, path: str) -> bool:
    if should_skip_content_type(content_type):
        return True
    lower = path.lower()
    if lower.endswith(".zip") or "/download" in lower:
        return True
    if content_type:
        ct = content_type.lower()
        if ct.startswith("image/") or ct.startswith("video/"):
            return True
    return False


def _redact(text: str) -> str:
    text = _SECRET_JSON_RE.sub(r'\1"[REDACTED]"', text)
    return _BEARER_RE.sub("Bearer [REDACTED]", text)


def preview_body(content: bytes, content_type: str | None = None) -> str:
    """Decode and truncate body for logs; redact obvious secret patterns."""
    if not content:
        return ""
    if is_likely_binary(content_type, ""):
        return f"[binary {len(content)} bytes]"
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return f"[binary {len(content)} bytes]"
    text = _redact(text)
    max_chars = preview_max_chars()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}…(+{len(text) - max_chars} chars)"


def content_length_int(response: Response) -> int | None:
    raw = response.headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def log_response_body(
    logger: logging.Logger,
    *,
    status: int,
    content_type: str | None,
    body: bytes,
    path: str,
    prefix: str = "response body",
) -> None:
    if not body_logging_enabled() or should_skip_path(path):
        return
    if is_likely_binary(content_type, path):
        logger.info(
            "%s status=%s path=%s preview=[binary %s bytes]",
            prefix,
            status,
            path,
            len(body),
        )
        return
    preview = preview_body(body, content_type)
    if not preview:
        return
    logger.info(
        "%s status=%s path=%s body_preview=%s",
        prefix,
        status,
        path,
        preview,
    )


async def read_and_log_response(
    logger: logging.Logger,
    request: Request,
    response: Response,
    *,
    prefix: str = "response body",
) -> Response:
    """Buffer a small response, log preview, return equivalent Response."""
    from starlette.responses import Response as StarletteResponse

    if not body_logging_enabled() or should_skip_path(request.url.path):
        return response

    content_type = response.headers.get("content-type")
    path = request.url.path
    status = response.status_code

    if should_skip_content_type(content_type) or is_likely_binary(
        content_type, path
    ):
        cl = content_length_int(response)
        size = cl if cl is not None else "unknown"
        logger.info(
            "%s status=%s path=%s preview=[binary %s bytes]",
            prefix,
            status,
            path,
            size,
        )
        return response

    cl = content_length_int(response)
    if cl is not None and cl > MAX_BODY_BYTES:
        logger.info(
            "%s status=%s path=%s preview=[large %s bytes]",
            prefix,
            status,
            path,
            cl,
        )
        return response

    if getattr(response, "body", None) is not None:
        body = bytes(response.body)
        log_response_body(
            logger,
            status=status,
            content_type=content_type,
            body=body,
            path=path,
            prefix=prefix,
        )
        return response

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.body_iterator:
        chunks.append(chunk)
        total += len(chunk)

    body = b"".join(chunks)
    log_response_body(
        logger,
        status=status,
        content_type=content_type,
        body=body,
        path=path,
        prefix=prefix,
    )
    return StarletteResponse(
        content=body,
        status_code=status,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=response.background,
    )
