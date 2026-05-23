"""Shared helpers for Forge OpenAPI export and merge."""

from __future__ import annotations

import importlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_DIR = REPO_ROOT / "docs" / "openapi"
SCALAR_DIR = REPO_ROOT / "docs" / "api" / "scalar"
BFF_STATIC_DIR = REPO_ROOT / "backend" / "services" / "bff" / "static" / "api-docs"
BFF_SPECS_DIR = BFF_STATIC_DIR / "specs"

# (export filename stem, import path, human label, default server URL for docs)
SERVICES: tuple[tuple[str, str, str, str], ...] = (
    ("bff", "services.bff.app:app", "BFF (Gateway)", "http://localhost:8000"),
    (
        "simulation",
        "services.simulation.app:app",
        "Simulation",
        "http://localhost:8001",
    ),
    ("runner", "services.runner.app:app", "Runner", "http://forge-runner:8080"),
    ("ccs", "services.ccs.app:app", "CCS", "http://localhost:8081"),
    ("ics", "services.ics.app:app", "ICS", "http://ics:8082"),
)

MERGE_ORDER = ("bff", "simulation", "runner", "ccs", "ics")

# Sidebar sub-groups within each per-service Scalar document (tag names from FastAPI).
SERVICE_TAG_GROUPS: dict[str, list[tuple[str, list[str]]]] = {
    "bff": [
        ("Health", ["health"]),
        ("Jobs & simulations", ["jobs", "simulations", "run-instructions"]),
        ("Conversations & AI", ["conversations", "ai"]),
        ("Viewer", ["viewer"]),
    ],
    "simulation": [
        ("Health", ["health"]),
        ("Jobs", ["jobs"]),
        ("Simulations", ["simulations", "run-instructions"]),
    ],
    "runner": [
        ("Health", ["health"]),
        ("Internal", ["internal"]),
    ],
    "ccs": [
        ("Health", ["health"]),
        ("Conversations", ["conversations"]),
        ("AI", ["ai"]),
    ],
    "ics": [
        ("Health", ["health"]),
        ("Classification", ["classification"]),
    ],
}


def _scalar_index_html(spec_prefix: str) -> str:
    """Scalar multi-source config: one OpenAPI file per microservice."""
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Forge APIs — Scalar</title>
  </head>
  <body>
    <div id="app"></div>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
    <script>
      Scalar.createApiReference("#app", {{
        theme: "default",
        sources: [
          {{ title: "BFF (Gateway)", slug: "bff", url: "{spec_prefix}/bff.json", default: true }},
          {{ title: "Simulation", slug: "simulation", url: "{spec_prefix}/simulation.json" }},
          {{ title: "Runner", slug: "runner", url: "{spec_prefix}/runner.json" }},
          {{ title: "CCS", slug: "ccs", url: "{spec_prefix}/ccs.json" }},
          {{ title: "ICS", slug: "ics", url: "{spec_prefix}/ics.json" }},
        ],
      }});
    </script>
  </body>
</html>
"""


def load_app(import_path: str) -> Any:
    module_path, attr = import_path.split(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr)


def export_openapi(app: Any) -> dict[str, Any]:
    return json.loads(json.dumps(app.openapi()))


def _collect_operation_tags(spec: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for path_item in (spec.get("paths") or {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.startswith("x-") or method == "parameters" or not isinstance(operation, dict):
                continue
            for tag in operation.get("tags") or []:
                found.add(tag)
    return found


def _build_x_tag_groups(service_id: str, spec: dict[str, Any]) -> list[dict[str, Any]]:
    groups_cfg = SERVICE_TAG_GROUPS.get(service_id, [])
    assigned: set[str] = set()
    groups: list[dict[str, Any]] = []
    op_tags = _collect_operation_tags(spec)
    for group_name, tag_names in groups_cfg:
        present = [t for t in tag_names if t in op_tags]
        if present:
            groups.append({"name": group_name, "tags": present})
            assigned.update(present)
    remaining = sorted(op_tags - assigned)
    if remaining:
        groups.append({"name": "Other", "tags": remaining})
    return groups


def _prefix_operation_id(service_id: str, operation: dict[str, Any]) -> None:
    op_id = operation.get("operationId")
    if not op_id:
        return
    prefix = f"{service_id}."
    if not op_id.startswith(prefix):
        operation["operationId"] = f"{prefix}{op_id}"


def annotate_service(
    spec: dict[str, Any],
    service_id: str,
    label: str,
    server_url: str,
) -> dict[str, Any]:
    """Prepare a per-service OpenAPI document for Scalar multi-source UI."""
    out = deepcopy(spec)
    out.setdefault("info", {})["x-forge-service"] = service_id
    out["info"]["x-forge-label"] = label
    out["servers"] = [{"url": server_url, "description": label}]

    tag_groups = _build_x_tag_groups(service_id, out)
    if tag_groups:
        out["x-tagGroups"] = tag_groups

    paths = out.get("paths") or {}
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.startswith("x-") or not isinstance(operation, dict):
                continue
            if method == "parameters":
                continue
            operation["x-forge-service"] = service_id
            operation["x-forge-original-path"] = path
            _prefix_operation_id(service_id, operation)

    return out


def _ref_name(ref: str) -> str | None:
    m = re.match(r"#/components/schemas/(.+)$", ref)
    return m.group(1) if m else None


def _rename_refs(obj: Any, renames: dict[str, str]) -> Any:
    if isinstance(obj, dict):
        if "$ref" in obj:
            name = _ref_name(obj["$ref"])
            if name and name in renames:
                return {"$ref": f"#/components/schemas/{renames[name]}"}
        return {k: _rename_refs(v, renames) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rename_refs(i, renames) for i in obj]
    return obj


def _merge_components(
    merged: dict[str, Any],
    spec: dict[str, Any],
    service_id: str,
) -> dict[str, str]:
    """Merge component definitions; return schema renames applied to this spec."""
    renames: dict[str, str] = {}
    components = spec.get("components") or {}
    if not components:
        return renames
    target = merged.setdefault("components", {})
    for section, items in components.items():
        if not isinstance(items, dict):
            continue
        bucket = target.setdefault(section, {})
        for name, definition in items.items():
            key = name if name not in bucket else f"{service_id}_{name}"
            if key != name:
                renames[name] = key
            bucket[key] = deepcopy(definition)
    if renames:
        if "paths" in spec:
            spec["paths"] = _rename_refs(spec["paths"], renames)
        if "components" in spec:
            spec["components"] = _rename_refs(spec["components"], renames)
    return renames


def _path_methods(path_item: dict[str, Any]) -> set[str]:
    return {
        m
        for m in path_item
        if m in {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    }


def _merged_tag(service_id: str, tag: str) -> str:
    return f"{service_id}-{tag}"


def merge_specs(specs: dict[str, dict[str, Any]], labels: dict[str, str]) -> dict[str, Any]:
    """Merge per-service OpenAPI documents (single-file fallback; Scalar uses multi-source)."""
    merged: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "Forge APIs (merged)",
            "version": "1.0.0",
            "description": (
                "Single-file catalog of all Forge FastAPI services. "
                "Prefer the Scalar UI at `/api-docs/` (one document per service). "
                "Per-service Swagger remains at each service `/docs`. "
                "Colliding routes (e.g. multiple `/health`) are under `/_internal/{service}/`."
            ),
        },
        "tags": [],
        "paths": {},
        "servers": [
            {"url": url, "description": label}
            for _sid, _imp, label, url in SERVICES
        ],
        "x-tagGroups": [],
    }

    occupied: dict[str, set[str]] = {}
    tag_group_entries: list[dict[str, Any]] = []

    for service_id in MERGE_ORDER:
        spec = specs.get(service_id)
        if not spec:
            continue
        label = labels.get(service_id, service_id)
        spec_copy = deepcopy(spec)
        _merge_components(merged, spec_copy, service_id)

        for tag in spec_copy.get("tags") or []:
            if isinstance(tag, dict) and "name" in tag:
                raw_name = tag["name"]
                merged["tags"].append(
                    {
                        **tag,
                        "name": _merged_tag(service_id, raw_name),
                        "description": f"[{label}] {tag.get('description', '')}".strip(),
                    }
                )

        paths = spec_copy.get("paths") or {}
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            methods = _path_methods(path_item)
            conflict = bool(methods & occupied.get(path, set()))
            target_path = path
            if conflict:
                target_path = f"/_internal/{service_id}{path}"

            dest = merged["paths"].setdefault(target_path, {})
            for method, operation in path_item.items():
                if method not in methods:
                    if method == "parameters":
                        dest.setdefault("parameters", operation)
                    continue
                op = deepcopy(operation)
                op["tags"] = [_merged_tag(service_id, t) for t in op.get("tags") or ["default"]]
                if conflict:
                    op["description"] = (
                        f"{op.get('description', '')}\n\n"
                        f"**Namespaced path** (collision with another service). "
                        f"**Actual URL on {label}:** `{path}`"
                    ).strip()
                    op["x-forge-namespaced"] = True
                dest[method] = op
                occupied.setdefault(target_path, set()).add(method)
                occupied.setdefault(path, set()).add(method)

        for group_name, tag_names in SERVICE_TAG_GROUPS.get(service_id, []):
            merged_tags = [_merged_tag(service_id, t) for t in tag_names]
            tag_group_entries.append({"name": f"{label} — {group_name}", "tags": merged_tags})

    merged["x-tagGroups"] = tag_group_entries
    return merged


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def sync_bff_static(exported: dict[str, dict[str, Any]], merged_path: Path) -> None:
    """Copy per-service specs and merged catalog beside BFF Scalar static assets."""
    BFF_STATIC_DIR.mkdir(parents=True, exist_ok=True)
    BFF_SPECS_DIR.mkdir(parents=True, exist_ok=True)

    for service_id, spec in exported.items():
        write_json(BFF_SPECS_DIR / f"{service_id}.json", spec)

    dest_merged = BFF_STATIC_DIR / "forge-merged.json"
    dest_merged.write_text(merged_path.read_text(encoding="utf-8"), encoding="utf-8")

    BFF_STATIC_DIR.joinpath("index.html").write_text(
        _scalar_index_html("/api-docs/specs"),
        encoding="utf-8",
    )

    SCALAR_DIR.mkdir(parents=True, exist_ok=True)
    SCALAR_DIR.joinpath("index.html").write_text(
        _scalar_index_html("/openapi"),
        encoding="utf-8",
    )
