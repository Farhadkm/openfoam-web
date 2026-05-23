# OpenAPI export and merged Scalar docs

Generates committed OpenAPI JSON under `docs/openapi/` and syncs per-service specs plus Scalar `index.html` into the BFF static bundle for `/api-docs`.

## Regenerate

From repo root:

```bash
make openapi
# or
./scripts/openapi/export_and_merge.sh
```

Requires Python 3.12+ and backend dependencies (`pip install -r backend/requirements.txt`).

## Outputs

| File | Description |
|------|-------------|
| `docs/openapi/bff.json` | BFF gateway (stub + health) |
| `docs/openapi/simulation.json` | Jobs, simulations, run instructions |
| `docs/openapi/runner.json` | Internal runner |
| `docs/openapi/ccs.json` | Conversations + AI |
| `docs/openapi/ics.json` | Intent classification |
| `docs/openapi/forge-merged.json` | Single-file merged catalog (fallback) |
| `backend/services/bff/static/api-docs/index.html` | Scalar multi-source UI |
| `backend/services/bff/static/api-docs/specs/*.json` | Per-service specs served to Scalar |

Scalar uses **one document per service** (`sources[]` in `index.html`). Sidebar sub-groups use `x-tagGroups` from `SERVICE_TAG_GROUPS` in `_lib.py`.

## View Scalar UI

- **BFF (Compose):** http://localhost:8000/api-docs/ — pick BFF / Simulation / Runner / CCS / ICS at the top
- **Static (no stack):** `python3 -m http.server 8765 --directory docs` then http://localhost:8765/api/scalar/

Per-service Swagger is unchanged (`/docs` on each FastAPI app). See [docs/api/README.md](../../docs/api/README.md).
