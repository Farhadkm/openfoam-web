"""Shared Vertex AI / Google credentials helpers for backend agent services."""

from __future__ import annotations

import json
import os

import vertexai

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")

_vertex_initialized = False

_GOOGLE_ADC_TYPES = frozenset(
    {
        "authorized_user",
        "service_account",
        "external_account",
        "external_account_authorized_user",
        "impersonated_service_account",
        "gdch_service_account",
    }
)


def _default_credentials_path() -> str:
    return "/app/credentials/key.json"


def credential_file_path() -> str | None:
    p = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if p and os.path.isfile(p):
        return p
    default = _default_credentials_path()
    if os.path.isfile(default):
        return default
    return None


def ensure_default_credentials_env() -> None:
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    path = credential_file_path()
    if path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path


def validate_google_credential_json(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read Google credentials JSON at {path}: {exc}") from exc
    cred_type = data.get("type")
    if cred_type not in _GOOGLE_ADC_TYPES:
        raise RuntimeError(
            f"Google credentials at {path} are invalid (type is {cred_type!r}; expected one of "
            f"{sorted(_GOOGLE_ADC_TYPES)}). "
            "Use a GCP service account JSON with Vertex AI / Gemini access."
        )


def credentials_health() -> dict:
    path = credential_file_path()
    if not path:
        return {"ok": False, "path": None, "detail": "No credentials file found."}
    try:
        validate_google_credential_json(path)
    except RuntimeError as exc:
        return {"ok": False, "path": path, "detail": str(exc)}
    return {"ok": True, "path": path, "detail": None}


def ensure_vertex() -> None:
    global _vertex_initialized
    if _vertex_initialized:
        return
    ensure_default_credentials_env()
    if not PROJECT_ID:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT_ID is not set")
    path = credential_file_path()
    if not path:
        raise RuntimeError(
            "No Google credentials file. Set GOOGLE_APPLICATION_CREDENTIALS or mount "
            "/app/credentials/key.json with a valid service account JSON."
        )
    validate_google_credential_json(path)
    vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
    _vertex_initialized = True
