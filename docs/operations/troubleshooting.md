# Troubleshooting

Detailed user-facing notes: root [README.md](../../README.md#common-troubleshooting).

## Job fails immediately

- ZIP layout: `system/` at case root vs nested folder — adjust commands (`cd myCase && …`)
- Wrong solver sequence for the case
- Read **Log** in UI or `/jobs/<id>/forge.log`

## Empty case in solver container (AWS)

- `JOBS_VOLUME_NAME` must match across backend, runner, and child container
- See [deploy/aws/README.md](../../deploy/aws/README.md#jobs-volume-solver-runs) (volume naming)

## VTK viewer blank

- Run `foamToVTK` (or equivalent) so `case/VTK/` exists
- Verify `NEXT_PUBLIC_TRAME_VIEWER_URL` at frontend **build** time
- Check `docker logs` for trame-viewer

## AI assistant unavailable

- `docker compose ps` — `ai` container up
- `GET /health` on port 8081
- Valid `backend/credentials/key.json` and Vertex-enabled GCP project
- Browser must reach `NEXT_PUBLIC_AI_WS_URL` host (not only server localhost)

## macOS mount errors

Use named volume `jobs_data`; avoid host bind mounts into nested containers. `docker compose down && docker compose up --build`
