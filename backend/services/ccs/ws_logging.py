"""WebSocket chat logging for CCS (conversation-scoped, truncated previews)."""

from __future__ import annotations

import logging
from typing import Any

from shared.payload_preview import preview_max_chars, preview_ws_payload

_logger = logging.getLogger(__name__)


def log_ws_inbound(conversation_id: str | None, payload: dict[str, Any]) -> None:
    from shared.conversation_tracing import record_ws_event

    record_ws_event("inbound", payload)
    cid = conversation_id or "unassigned"
    _logger.info(
        "ws inbound conversation_id=%s type=%s payload=%s",
        cid,
        payload.get("type"),
        preview_ws_payload(payload),
    )


def log_ws_outbound(conversation_id: str | None, payload: dict[str, Any]) -> None:
    from shared.conversation_tracing import record_ws_event

    record_ws_event("outbound", payload)
    cid = conversation_id or "unassigned"
    _logger.info(
        "ws outbound conversation_id=%s type=%s payload=%s",
        cid,
        payload.get("type"),
        preview_ws_payload(payload),
    )
