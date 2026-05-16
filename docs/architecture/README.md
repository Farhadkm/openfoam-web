# Architecture (entry point)

OpenFOAM web runs CFD cases from a browser: upload a case ZIP, execute OpenFOAM in Docker, inspect logs, download results, visualize VTK, and optionally chat with a Vertex AI assistant.

## Architecture style

- **Microservices in Docker Compose** (not a monolith)
- **Shared volume** (`jobs_data`) as the filesystem source of truth per job
- **MongoDB** for job metadata only
- **Browser** talks REST to backend, WebSocket to AI, postMessage + iframe to Trame

## Primary services

| Service | Port (local) | Responsibility |
|---------|----------------|----------------|
| frontend | 3000 | Next.js UI |
| backend | 8000 | Jobs API, ZIP extract, runner orchestration |
| openfoam-runner | internal | Start OpenFOAM containers |
| trame-viewer | 8090 | VTK visualization (wslink) |
| ai | 8081 | Gemini chat WebSocket |
| mongo | 127.0.0.1:27017 | Job persistence |

## Key dependencies

- Docker Engine (runner uses socket for child containers)
- OpenFOAM image: `opencfd/openfoam-run` (see Compose env)
- Google Cloud Vertex AI (optional; AI service)
- AWS (dev only): ECR, EC2, S3, Secrets Manager — see [deploy/aws/README.md](../../deploy/aws/README.md)

## Documentation map

- [System overview](./system-overview.md)
- [Service map](./service-map.md)
- [Data flow](./data-flow.md)
- [Architecture decisions](./decisions.md)
- [Development setup](../development/setup.md)
- [Deployment](../operations/deployment.md)

## Diagram

See the mermaid diagram in the root [README.md](../../README.md#architecture).
