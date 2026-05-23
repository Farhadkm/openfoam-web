#!/usr/bin/env bash
# Run Forge chatbot eval tests (pytest + optional DeepEval judge).
#
# Cases load from backend/tests/eval/cases/*.json (see load_cases.py).
#
# Usage:
#   ./scripts/run-chatbot-eval.sh structural              # full.json (50 cases)
#   ./scripts/run-chatbot-eval.sh structural smoke.json   # quick subset
#   ./scripts/run-chatbot-eval.sh structural run-page.json job-page.json
#   ./scripts/run-chatbot-eval.sh structural full.json --case run-param-01
#   ./scripts/run-chatbot-eval.sh list smoke.json
#   ./scripts/run-chatbot-eval.sh deepeval smoke.json
#
# Environment:
#   FORGE_EVAL_CASES     Comma-separated suite files (default: full.json)
#   FORGE_EVAL_CASE_ID   Single case id filter (optional)
#   FORGE_EVAL_JUDGE=1   Enable DeepEval GEval judge (deepeval mode sets this)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

export PYTHONPATH=.
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/backend/credentials/key.json}"

if [[ -z "${GOOGLE_CLOUD_PROJECT_ID:-}" && -f "$GOOGLE_APPLICATION_CREDENTIALS" ]]; then
  GOOGLE_CLOUD_PROJECT_ID="$(python3 -c "import json; print(json.load(open('$GOOGLE_APPLICATION_CREDENTIALS')).get('project_id',''))")"
  export GOOGLE_CLOUD_PROJECT_ID
fi
if [[ -z "${GOOGLE_CLOUD_PROJECT_ID:-}" ]]; then
  echo "Set GOOGLE_CLOUD_PROJECT_ID or use a service account key.json with project_id." >&2
  exit 1
fi

MODE="${1:-structural}"
shift || true

FORGE_EVAL_CASES="${FORGE_EVAL_CASES:-full.json}"
FORGE_EVAL_CASE_ID="${FORGE_EVAL_CASE_ID:-}"
EXTRA_JSON=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --case)
      FORGE_EVAL_CASE_ID="${2:?--case requires an id}"
      shift 2
      ;;
    *.json|cases/*)
      EXTRA_JSON+=("$1")
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 {structural|deepeval|list|validate} [suite.json ...] [--case ID]" >&2
      exit 1
      ;;
  esac
done

if [[ ${#EXTRA_JSON[@]} -gt 0 ]]; then
  FORGE_EVAL_CASES=$(IFS=,; echo "${EXTRA_JSON[*]}")
fi

export FORGE_EVAL_CASES
export FORGE_EVAL_CASE_ID

VENV="$ROOT/backend/.venv"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck source=/dev/null
source "$VENV/bin/activate"
pip install -q -r requirements.txt -r requirements-eval.txt

case "$MODE" in
  structural)
    pytest tests/eval/test_chatbot_eval.py -m "structural and slow" -v --tb=short
    ;;
  deepeval)
    export FORGE_EVAL_JUDGE=1
    deepeval test run tests/eval/test_chatbot_eval.py -m "deepeval and slow" -v
    ;;
  list)
    python -m tests.eval.load_cases list
    ;;
  validate)
    if [[ ${#EXTRA_JSON[@]} -gt 0 ]]; then
      python -m tests.eval.validate_cases_json "${EXTRA_JSON[@]}"
    else
      python -m tests.eval.validate_cases_json
    fi
    ;;
  *)
    echo "Usage: $0 {structural|deepeval|list|validate} [suite.json ...] [--case ID]" >&2
    exit 1
    ;;
esac
