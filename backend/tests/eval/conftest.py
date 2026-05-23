"""Pytest fixtures for Forge chatbot eval."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from shared.vertex import credentials_health

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def vertex_configured() -> bool:
    if not credentials_health().get("ok", False):
        return False
    if os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip():
        return True
    path = credentials_health().get("path")
    if path and Path(path).is_file():
        import json

        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return bool(data.get("project_id"))
        except (OSError, json.JSONDecodeError):
            return False
    return False


def deepeval_judge_enabled() -> bool:
    return os.getenv("FORGE_EVAL_JUDGE", "").lower() in ("1", "true", "yes")


@pytest.fixture(scope="session")
def require_vertex() -> None:
    if not credentials_health().get("ok", False):
        pytest.skip(
            "Vertex credentials missing. Mount backend/credentials/key.json and set "
            "GOOGLE_APPLICATION_CREDENTIALS."
        )
    if not os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip():
        path = credentials_health().get("path")
        if path and Path(path).is_file():
            import json

            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                pid = data.get("project_id")
                if pid:
                    os.environ["GOOGLE_CLOUD_PROJECT_ID"] = str(pid)
            except (OSError, json.JSONDecodeError):
                pass
    if not os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip():
        pytest.skip("GOOGLE_CLOUD_PROJECT_ID not set and not found in credentials JSON.")


@pytest.fixture
def default_creds_path() -> Path:
    return _BACKEND_ROOT / "credentials" / "key.json"
