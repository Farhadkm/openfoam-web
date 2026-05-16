# Service map

```
Browser
  ├─ REST ──────────────► backend (FastAPI) ──► MongoDB
  │                         │
  │                         └─ HTTP ──► openfoam-runner ──► Docker ──► OpenFOAM container
  ├─ WebSocket ───────────► ai (FastAPI) ──► Vertex AI
  └─ iframe + postMessage ► trame-viewer (Trame/VTK) ── reads jobs_data
```

## Service directories

| Directory | API surface | Notes |
|-----------|-------------|--------|
| `frontend/` | — | Next.js; env at build time for public URLs |
| `backend/` | `:8000` REST | Job CRUD, logs, downloads |
| `openfoam-runner/` | `:8080` internal | Not published to host in Compose |
| `trame-viewer/` | `:8090` HTTP/WS | Serves bridge JS for parent page |
| `ai/` | `:8081` HTTP + `/ws` | System prompt in `prompt.py` |

## Shared configuration

- `JOBS_ROOT` — mount path inside containers (default `/jobs`)
- `JOBS_VOLUME_NAME` — Docker volume name passed into child OpenFOAM containers (critical on AWS)
- `MONGODB_URI` / `MONGODB_DB` — backend only
