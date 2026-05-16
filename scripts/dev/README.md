# Development scripts

Use `make` targets or Docker Compose directly.

```bash
make up          # docker compose up --build
make logs        # follow all service logs
make ps          # service status
```

Service-specific rebuild:

```bash
docker compose up --build backend
```
