# API documentation

## Unified Scalar reference (all services)

| Where | URL |
|-------|-----|
| **BFF (recommended)** | http://localhost:8000/api-docs/ |
| **Static files** | Open `docs/api/scalar/index.html` via a local server (see below) |

Scalar loads **one OpenAPI document per microservice** (multi-source config). Use the document picker at the top to switch between BFF, Simulation, Runner, CCS, and ICS. Within each document, the sidebar uses **`x-tagGroups`** for logical sections (Health, Jobs, Conversations, Internal, etc.).

| Artifact | Path |
|----------|------|
| Per-service specs | `docs/openapi/{bff,simulation,runner,ccs,ics}.json` |
| Merged fallback (single file) | `docs/openapi/forge-merged.json` |
| BFF static copy | `backend/services/bff/static/api-docs/specs/*.json` |

Regenerate after API changes:

```bash
make openapi
```

Static preview without Compose:

```bash
python3 -m http.server 8765 --directory docs
# http://localhost:8765/api/scalar/  (specs at /openapi/*.json)
```

**Grouping model:** Option A — Scalar `sources[]` (one spec per service). Tags stay as defined in each FastAPI app (`health`, `jobs`, …). Sub-groups come from `x-tagGroups` in `scripts/openapi/_lib.py` (`SERVICE_TAG_GROUPS`). `operationId` values are prefixed (`bff.health_health_get`, `simulation.list_jobs_…`) for search. The merged file keeps `/{service}-{tag}` tags and `/_internal/{service}/` paths only for route collisions; prefer the multi-source UI for day-to-day browsing.

Per-service Swagger (`/docs`) is unchanged. Trame-viewer has no OpenAPI.

## Public REST API (browser)

- **BFF OpenAPI:** `http://localhost:8000/docs` (and `/redoc`) — stub docs for all browser-facing proxy routes; see `backend/services/bff/openapi.py`
- **Implementation:** `backend/services/bff/` proxies to simulation, CCS, and trame-viewer
- **Jobs / simulations:** proxied to simulation (`/api/jobs`, `/api/simulations`, `/api/run-instructions`)
- **Conversations / AI:** proxied to CCS (`/api/conversations`, `/api/ai/ws`, `/api/ai/generate-thumbnail`)
- **VTK viewer:** proxied to trame-viewer (`/viewer`, WebSocket `/viewer/ws`)

## CCS (conversations + chat)

| Method | BFF path | CCS path | Description |
|--------|----------|----------|-------------|
| `POST` | `/api/conversations` | same | Create conversation |
| `GET` | `/api/conversations` | same | List conversations |
| `GET` | `/api/conversations/{id}` | same | Get + messages |
| `DELETE` | `/api/conversations/{id}` | same | Delete |
| `GET` | `/api/conversations/{id}/messages` | same | Message history |
| `WS` | `/api/ai/ws` | `/ws` | Streaming chat |
| `POST` | `/api/ai/generate-thumbnail` | `/generate-thumbnail` | Thumbnail PNG |

## Trame viewer (VTK iframe)

| Kind | BFF path | trame-viewer path | Description |
|------|----------|-------------------|-------------|
| HTTP | `/viewer`, `/viewer/{path}` | `/`, `/{path}` | Trame app + static assets |
| WS | `/viewer/ws` | `/ws` | wslink session |

Direct CCS Swagger (ops): `http://localhost:8081/docs`. Storage is in-memory on CCS (see `backend/services/ccs/README.md`).

## Internal APIs

| Service | Base | Swagger (default Compose) |
|---------|------|---------------------------|
| simulation | `http://simulation:8001` | `docker compose exec simulation curl http://localhost:8001/docs` |
| forge-runner | `http://forge-runner:8080` | `docker compose exec forge-runner curl http://localhost:8080/docs` |
| ics | `http://ics:8082` | `docker compose exec ics curl http://localhost:8082/docs` |
| trame-viewer | `http://trame-viewer:8090` | **No OpenAPI** — Trame/wslink + `postMessage` bridge |

## AI WebSocket protocol

Message types and XML response contract: `backend/services/ccs/app.py`, `backend/services/ccs/prompt.py`, and [data flow](../architecture/data-flow.md).
