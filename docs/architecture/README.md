# Architecture (entry point)

Forge runs CFD cases from a browser: upload a case ZIP, execute solvers in Docker, inspect logs, download results, visualize VTK, and optionally chat with a Vertex AI assistant.

## Architecture style

- **Microservices in Docker Compose** (not a monolith)
- **Shared volume** (`jobs_data`) as the filesystem source of truth per job
- **MongoDB** for job metadata only
- **Browser** talks REST to BFF, WebSocket to CCS, postMessage + iframe to Trame

## Primary services

| Service | Port (local) | Responsibility |
|---------|----------------|----------------|
| frontend | 3000 | Next.js UI |
| bff | 8000 | Browser API gateway (proxies to simulation) |
| simulation | internal | Jobs + simulations API, ZIP extract, runner orchestration |
| ccs | 8081 | Chat WebSocket (Gemini) |
| ics | internal | Intent classification |
| runner | internal | Start solver containers (Compose service: `forge-runner`) |
| trame-viewer (`backend/services/trame-viewer/`) | 8090 | VTK visualization (wslink); separate image |
| pss | internal 8003 | XGBoost training/prediction on mass-run data (BFF-proxied) |
| mongo | 127.0.0.1:27017 | Job persistence |

## Key dependencies

- Docker Engine (runner uses socket for child containers)
- OpenFOAM image: `opencfd/openfoam-run` (see Compose env)
- Google Cloud Vertex AI (optional; CCS service)
- AWS (dev only): ECR, EC2, S3, Secrets Manager — see [deploy/aws/README.md](../../deploy/aws/README.md)

## Documentation map

- **[LLM project context](../llm-context.md)** — dense one-page brief for AI agents (identity, architecture, env vars, conventions)
- **[Service map](./service-map.md)** — ports, health probes, mermaid diagram, caller/callee table
- Per-service READMEs: `backend/services/{bff,simulation,pss,runner,ccs,ics,trame-viewer}/README.md`
- [System overview](./system-overview.md)
- [Data flow](./data-flow.md)
- [Architecture decisions](./decisions.md)
- [Development setup](../development/setup.md)
- [Deployment](../operations/deployment.md)

## Diagram

See the mermaid diagram in [service-map.md](./service-map.md) and the root [README.md](../../README.md#architecture).
