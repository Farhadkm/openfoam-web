# API documentation

## Public REST API

- **OpenAPI:** run backend locally and open `http://localhost:8000/docs`
- **Implementation:** `backend/` (job upload, status, logs, outputs, download)

## Internal APIs

| Service | Base | Consumers |
|---------|------|-----------|
| openfoam-runner | `http://openfoam-runner:8080` | backend only |
| ai | `ws://…:8081/ws` | browser (WebSocket) |
| trame-viewer | HTTP + wslink `/ws` | browser iframe |

Internal runner routes are not exposed on the host in default Compose.

## AI protocol

WebSocket message types and XML response contract: `ai/server.py`, `ai/prompt.py`, and [data flow](../architecture/data-flow.md).
