# Test scripts

No automated test runner is wired at repo root yet.

## Manual smoke test

1. `docker compose up --build`
2. Upload minimal case ZIP (see root README)
3. Run `blockMesh && simpleFoam` or case-appropriate commands
4. Confirm log output and job completion in UI
5. Optional: `foamToVTK` then open visualize page

## Health checks

```bash
curl -s http://localhost:8000/docs >/dev/null && echo backend ok
curl -s http://localhost:8081/health
```

Add `pytest` / Playwright commands here when test suites are introduced.
