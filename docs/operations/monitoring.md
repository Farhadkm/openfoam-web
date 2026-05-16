# Monitoring

## Local / dev

| Check | Command / URL |
|-------|----------------|
| Service status | `docker compose ps` |
| Logs | `docker compose logs -f backend` (or other service) |
| Backend health | `http://localhost:8000/docs` |
| AI health | `http://localhost:8081/health` |
| MongoDB | `mongosh` to `127.0.0.1:27017` (host-mapped in Compose) |

## AWS dev EC2

- **SSM session:** `aws ssm start-session --target <instance-id>`
- On host: `docker compose -f docker-compose.aws-dev.yml ps` and `docker logs`
- GitHub Actions: deploy workflow run history for build/push failures

## Signals to watch

- Job stuck in running — runner or OpenFOAM container exit code; read `openfoam.log`
- Viewer disconnect — large VTK payloads, `TRAME_WS_MAX_MSG_SIZE`, client refresh
- AI errors — Vertex credentials, `GOOGLE_CLOUD_PROJECT_ID`, quota

No centralized APM is configured in this repository.
