# Development setup

## Prerequisites

- Docker Desktop or Docker Engine
- (Optional) Google Cloud project with Vertex AI for AI chat
- (Optional) Node.js only if running frontend outside Compose

## Quick start

```bash
cd /path/to/forge
docker compose up --build
```

| URL | Service |
|-----|---------|
| http://localhost:3000 | UI |
| http://localhost:8000/docs | BFF OpenAPI (jobs, simulations, AI, viewer proxy) |
| http://localhost:8000/viewer | VTK viewer (proxied to trame-viewer) |

## Environment variables

Copy `.env.example` to `.env` for local overrides. Compose sets most defaults.

**AI (required for chat):**

- `GOOGLE_CLOUD_PROJECT_ID`
- Service account JSON at `backend/credentials/key.json` (mounted in Compose)

**Frontend (build args in Compose):**

- `NEXT_PUBLIC_API_URL` — browser-reachable BFF base (e.g. `http://localhost:8000`). REST, AI WebSocket (`/api/ai/ws`), and Trame iframe (`/viewer`) are derived from this.

## Case upload

See root [README.md](../../README.md#case-upload-format-zip).

## AWS dev host

See [deploy/aws/README.md](../../deploy/aws/README.md).
