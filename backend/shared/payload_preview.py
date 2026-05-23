"""Truncate JSON/text payloads for logs and trace span attributes."""

from __future__ import annotations

import json
import os
from typing import Any


def preview_max_chars() -> int:
    try:
        return max(0, int(os.getenv("LOG_HTTP_BODY_MAX", "1024")))
    except ValueError:
        return 1024


def preview_ws_payload(payload: dict[str, Any]) -> str:
    """Serialize a WS JSON payload for logs/traces; truncate long message bodies."""
    max_chars = preview_max_chars()
    if max_chars == 0:
        return "[preview disabled]"

    out = dict(payload)
    msg_type = out.get("type")
    if msg_type == "init":
        if isinstance(out.get("inputFields"), list):
            out["inputFields"] = f"[{len(out['inputFields'])} fields]"
        if isinstance(out.get("viewerState"), dict):
            keys = list(out["viewerState"].keys())[:12]
            out["viewerState"] = f"[keys: {keys}]"
    elif msg_type == "user_message" and isinstance(out.get("message"), str):
        text = out["message"]
        if len(text) > max_chars:
            out["message"] = text[:max_chars] + f"... [{len(text)} chars]"
    elif msg_type == "assistant_message" and isinstance(out.get("message"), str):
        text = out["message"]
        if len(text) > max_chars:
            out["message"] = text[:max_chars] + f"... [{len(text)} chars]"
    elif msg_type == "intent_classification" and isinstance(out.get("intents"), list):
        out["intents"] = f"[{len(out['intents'])} intents]"

    try:
        raw = json.dumps(out, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        raw = str(out)
    if len(raw) > max_chars:
        return raw[:max_chars] + f"... [{len(raw)} chars]"
    return raw
