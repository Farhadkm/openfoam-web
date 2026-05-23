"""Load Forge chatbot eval cases from JSON files under tests/eval/cases/."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from tests.eval.chatbot_cases import ChatbotCase

CASES_DIR = Path(__file__).resolve().parent / "cases"
DEFAULT_SUITE = "full.json"

_REQUIRED_KEYS = ("id", "description", "page_context", "user_message")


class CaseLoadError(Exception):
    """Raised when case JSON cannot be loaded or validated."""


def _resolve_path(spec: str | Path) -> Path:
    p = Path(spec)
    if p.is_file():
        return p.resolve()
    candidate = CASES_DIR / spec
    if not spec.endswith(".json") and not (CASES_DIR / spec).exists():
        candidate = CASES_DIR / f"{spec}.json"
    if candidate.is_file():
        return candidate.resolve()
    raise CaseLoadError(
        f"Case file not found: {spec!r} (looked at {p.resolve() if p.is_absolute() else p} "
        f"and {candidate})"
    )


def _validate_case(case: Any, *, source: Path, index: int) -> ChatbotCase:
    if not isinstance(case, dict):
        raise CaseLoadError(f"{source}: case[{index}] must be an object, got {type(case).__name__}")
    missing = [k for k in _REQUIRED_KEYS if not case.get(k)]
    if missing:
        raise CaseLoadError(f"{source}: case[{index}] missing required keys: {', '.join(missing)}")
    if not isinstance(case["id"], str) or not case["id"].strip():
        raise CaseLoadError(f"{source}: case[{index}] has invalid id")
    return case  # type: ignore[return-value]


def load_cases(path_or_paths: str | Path | list[str | Path]) -> list[ChatbotCase]:
    """Load and merge case lists from one or more JSON files (each file: JSON array)."""
    if isinstance(path_or_paths, (str, Path)):
        paths = [_resolve_path(path_or_paths)]
    else:
        if not path_or_paths:
            raise CaseLoadError("load_cases: at least one path is required")
        paths = [_resolve_path(p) for p in path_or_paths]

    merged: list[ChatbotCase] = []
    seen_ids: set[str] = set()

    for path in paths:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CaseLoadError(f"Cannot read {path}: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CaseLoadError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, list):
            raise CaseLoadError(f"{path}: root must be a JSON array, got {type(data).__name__}")

        file_ids: set[str] = set()
        for i, item in enumerate(data):
            case = _validate_case(item, source=path, index=i)
            cid = case["id"]
            if cid in file_ids:
                raise CaseLoadError(f"{path}: duplicate id {cid!r} in same file")
            file_ids.add(cid)
            if cid in seen_ids:
                raise CaseLoadError(f"Duplicate id {cid!r} across loaded files (already in merged set)")
            seen_ids.add(cid)
            merged.append(case)

    return merged


def _cases_spec_from_env() -> list[str]:
    raw = os.getenv("FORGE_EVAL_CASES", "").strip()
    if not raw:
        return [DEFAULT_SUITE]
    return [part.strip() for part in raw.split(",") if part.strip()]


def get_eval_cases() -> list[ChatbotCase]:
    """Cases for pytest/scripts: FORGE_EVAL_CASES + optional FORGE_EVAL_CASE_ID filter."""
    cases = load_cases(_cases_spec_from_env())
    case_id = os.getenv("FORGE_EVAL_CASE_ID", "").strip()
    if not case_id:
        return cases
    filtered = [c for c in cases if c["id"] == case_id]
    if not filtered:
        known = ", ".join(c["id"] for c in cases[:20])
        suffix = "..." if len(cases) > 20 else ""
        raise CaseLoadError(
            f"FORGE_EVAL_CASE_ID={case_id!r} not found in loaded cases ({len(cases)} cases). "
            f"Known ids include: {known}{suffix}"
        )
    return filtered


def list_cases(path_or_paths: str | Path | list[str | Path] | None = None) -> None:
    """Print case ids (for scripts). Uses FORGE_EVAL_CASES when path_or_paths is None."""
    if path_or_paths is None:
        cases = get_eval_cases()
        specs = _cases_spec_from_env()
        label = ", ".join(specs)
    else:
        cases = load_cases(path_or_paths)
        label = str(path_or_paths)
    print(f"{len(cases)} case(s) from {label}")
    for c in cases:
        print(f"  {c['id']} - {c.get('description', '')}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_cases(sys.argv[2:] if len(sys.argv) > 2 else None)
    else:
        list_cases()


if __name__ == "__main__":
    main()
