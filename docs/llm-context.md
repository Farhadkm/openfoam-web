# Forge — LLM project context

Dense paste-in reference for AI agents. **No secret values** — env names and paths only. Max ~8000 chars for GPT custom instructions.

## What Forge is

Browser app for **CFD**: upload OpenFOAM case ZIP → run solver/mesh in **Docker** → stream **logs** → visualize **`case/VTK/`** in embedded **Trame** viewer → optional **Vertex AI (Gemini)** assistant on run page.

**Flow:** ZIP → simulation extracts to `/jobs/<id>/case/` → `POST /internal/run` on runner → OpenFOAM child container → logs at `/jobs/<id>/forge.log` → Trame reads VTK from same volume. Commands: `bash -lc "<cmds>"` after sourcing OpenFOAM `bashrc`.

## Repo layout

| Path | Role |
|------|------|
| `frontend/` | Next.js — jobs, logs, VTK controls, AI chat |
| `backend/services/bff/` | Browser REST/WS gateway (**8000**) |
| `backend/services/simulation/` | Jobs, templates, MongoDB, ZIP, runner calls (**8001** internal) |
| `backend/services/runner/` | Docker socket → ephemeral OpenFOAM containers (**8080**, Compose: `forge-runner`) |
| `backend/services/ccs/` | Chat WebSocket + Gemini (**8081**) |
| `backend/services/ics/` | Intent classification (**8082** internal) |
| `backend/services/trame-viewer/` | Trame + VTK; separate image (**8090**) |
| `deploy/aws/` | Dev-only Terraform + EC2 Compose |
| `docker-compose.yml` | Local full stack |

**Job files:** volume `forge-jobs-data` (`jobs_data`) at `/jobs/<job_id>/` — shared by simulation, runner, solver child, trame-viewer.

## Architecture (brief)

- Microservices in **Docker Compose**; **MongoDB** = job/sim metadata only (not case blobs).
- **Filesystem truth:** named volume `jobs_data` under `/jobs/<job_id>/`.
- **Browser:** REST (+ job log WS) → **BFF** only; WS → **CCS**; iframe + postMessage → **trame-viewer** (`frontend/lib/trameBridge.ts`).
- **Solver:** only runner mounts Docker socket; children use same **`JOBS_VOLUME_NAME`** as simulation. No host bind-mounts for case data (macOS issues).

Ports (local): UI `3000`, bff `8000`, ccs `8081`, trame `8090`, mongo `127.0.0.1:27017`. Full diagram: `docs/architecture/service-map.md`.

## Caller → callee

| Caller | Callee | Notes |
|--------|--------|-------|
| frontend | bff | `NEXT_PUBLIC_API_URL` → `/api/*` |
| frontend | ccs | `NEXT_PUBLIC_AI_WS_URL` → `/ws` |
| frontend | trame-viewer | `NEXT_PUBLIC_TRAME_VIEWER_URL`; postMessage + wslink |
| bff | simulation | `SIMULATION_SERVICE_URL` HTTP/WS proxy |
| simulation | mongo | `MONGODB_URI`, `MONGODB_DB` |
| simulation | runner | `RUNNER_URL` → `POST /internal/run` |
| ccs | ics | `ICS_URL` → `/classify` |
| ccs, ics | Vertex AI | `GOOGLE_CLOUD_PROJECT_ID`, credentials path |
| runner | Docker | Child containers + `JOBS_VOLUME_NAME` |

## Stack

Next.js + TS · FastAPI (shared `backend/` image) · MongoDB 7 · Compose · `opencfd/openfoam-run` · Trame/VTK/wslink · Vertex/Gemini (`backend/shared/vertex.py`) · AWS dev: Terraform/ECR/EC2 (`deploy/aws/`).

## Env vars (names only)

`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_TRAME_VIEWER_URL`, `NEXT_PUBLIC_AI_WS_URL`, `TRAME_INTERNAL_URL`, `SIMULATION_SERVICE_URL`, `CORS_ORIGINS`, `MONGODB_URI`, `MONGODB_DB`, `RUNNER_URL`, `JOBS_ROOT`, `JOBS_VOLUME_NAME`, `JOBS_VOLUME_MOUNT`, `OPENFOAM_IMAGE`, `OPENFOAM_BASHRC`, `GOOGLE_CLOUD_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, `GEMINI_MODEL`, `GEMINI_IMAGE_MODEL`, `ICS_URL`, `TRAME_WS_MAX_MSG_SIZE`, `WSLINK_HEART_BEAT`, `DEV_PUBLIC_HOST`, `DEV_EC2_INSTANCE_ID`, `ECR_REGISTRY`. Local: `.env.example` → `.env`. Creds (not in git): `backend/credentials/key.json`.

## Agent conventions

- Read `docs/architecture/`, `.cursor/rules/`, `backend/services/*/README.md` before non-trivial changes.
- Extend existing services; no parallel job paths, duplicate viewers, or MongoDB bypass for metadata.
- Never commit `key.json`, real `.env`, or TF state with secrets.
- AI XML contract: `backend/services/ccs/prompt.py`; client: `frontend/lib/aiChat.ts`.
- Update `docs/` when architecture or ops change.

## Local dev

`docker compose up --build` (root). Health: `curl localhost:8000/health`, `8081/health`. UI `3000`, BFF docs `8000/docs`, Trame `8090`. Wipe: `docker compose down -v`.

## Out of scope

Production deploy, K8s, committed secrets. AWS = **dev EC2 only**.

## Deeper docs

| Topic | Path |
|-------|------|
| Runbook, ZIP, troubleshooting | `README.md` |
| Architecture entry | `docs/architecture/README.md` |
| Service map (ports, mermaid) | `docs/architecture/service-map.md` |
| Data flow | `docs/architecture/data-flow.md` |
| ADRs | `docs/architecture/decisions.md` |
| Dev setup | `docs/development/setup.md` |
| AWS dev | `deploy/aws/README.md` |
| Tracing (local SigNoz :8080) | `docs/operations/monitoring.md` |
| Per-service APIs | `backend/services/{bff,simulation,runner,ccs,ics,trame-viewer}/README.md` |
| Cursor rules | `.cursor/rules/` (`10-project-context`, `20-architecture`, `40-security`) |

<!-- 4870 chars (limit 8000) -->
