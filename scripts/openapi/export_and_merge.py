#!/usr/bin/env python3
"""Export per-service OpenAPI JSON and merge into docs/openapi/forge-merged.json."""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root on sys.path so `backend` layout resolves when invoked from anywhere.
_REPO = Path(__file__).resolve().parents[2]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _lib import (  # noqa: E402
    MERGE_ORDER,
    OPENAPI_DIR,
    SERVICES,
    annotate_service,
    export_openapi,
    load_app,
    merge_specs,
    sync_bff_static,
    write_json,
)


def main() -> int:
    labels = {sid: label for sid, _imp, label, _url in SERVICES}
    exported: dict[str, dict] = {}

    for service_id, import_path, label, server_url in SERVICES:
        print(f"Exporting {service_id} ({import_path})...")
        app = load_app(import_path)
        raw = export_openapi(app)
        annotated = annotate_service(raw, service_id, label, server_url)
        out_path = OPENAPI_DIR / f"{service_id}.json"
        write_json(out_path, annotated)
        exported[service_id] = annotated
        print(f"  -> {out_path.relative_to(_REPO)} ({len(annotated.get('paths') or {})} paths)")

    merged = merge_specs(exported, labels)
    merged_path = OPENAPI_DIR / "forge-merged.json"
    write_json(merged_path, merged)
    sync_bff_static(exported, merged_path)

    path_count = len(merged.get("paths") or {})
    print(f"Merged -> {merged_path.relative_to(_REPO)} ({path_count} paths)")
    static = _REPO / "backend/services/bff/static/api-docs"
    print(f"BFF static -> {static.relative_to(_REPO)} (index.html + specs/*.json + forge-merged.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
