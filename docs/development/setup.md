# Development setup

## Prerequisites

- Docker Desktop or Docker Engine
- (Optional) Google Cloud project with Vertex AI for AI chat
- (Optional) Node.js only if running frontend outside Compose

## Quick start

```bash
cd /path/to/OpenFOAM
docker compose up --build
```

| URL | Service |
|-----|---------|
| http://localhost:3000 | UI |
| http://localhost:8000/docs | Backend OpenAPI |
| http://localhost:8090 | Trame (direct) |
| http://localhost:8081/health | AI health |

## Environment variables

Copy `.env.example` to `.env` for local overrides. Compose sets most defaults.

**AI (required for chat):**

- `GOOGLE_CLOUD_PROJECT_ID`
- Service account JSON at `ai/credentials/key.json` (mounted in Compose)

**Frontend (build args in Compose):**

- `NEXT_PUBLIC_TRAME_VIEWER_URL` — e.g. `http://localhost:8090`
- `NEXT_PUBLIC_AI_WS_URL` — e.g. `ws://localhost:8081/ws`

## Case upload

See root [README.md](../../README.md#case-upload-format-zip).

## AWS dev host

See [deploy/aws/README.md](../../deploy/aws/README.md).
