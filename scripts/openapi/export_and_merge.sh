#!/usr/bin/env bash
# Export per-service OpenAPI specs and merge for Scalar. Run from repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "${ROOT}/scripts/openapi/export_and_merge.py"
