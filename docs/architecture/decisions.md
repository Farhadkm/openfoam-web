# Architecture decisions

## ADR-001: Named Docker volume for job files

**Context:** Bind-mounting host paths into nested OpenFOAM containers fails on Docker Desktop for Mac.

**Decision:** Use Compose volume `jobs_data`; runner passes `JOBS_VOLUME_NAME` into child containers.

**Consequences:** All services must agree on volume name (especially `docker-compose.aws-dev.yml` on EC2).

## ADR-002: Separate runner service with Docker socket

**Context:** Backend should not hold Docker privileges.

**Decision:** `openfoam-runner` is internal-only and owns socket access.

**Consequences:** Network must allow backend → runner; runner API is not exposed on host port in default Compose.

## ADR-003: Trame in iframe with postMessage bridge

**Context:** Full Trame chrome is unnecessary; parent UI owns controls.

**Decision:** VTK-only iframe; `trameBridge.ts` and viewer-served `openfoam-bridge.js` exchange state.

**Consequences:** `NEXT_PUBLIC_TRAME_VIEWER_URL` must be browser-reachable; optional `sessionURL` for wslink.

## ADR-004: Vertex AI for assistant

**Context:** Need contextual help for OpenFOAM inputs and viewer.

**Decision:** Dedicated `ai` service with Gemini via Vertex; credentials via mounted JSON or AWS Secrets Manager on dev EC2.

**Consequences:** AI is optional for core job execution; invalid credentials fail chat only.

## ADR-005: AWS dev only in-repo

**Context:** Team needs a shared dev host without production scope in this repository.

**Decision:** Terraform + GitHub Actions on branch `develop`; no `main` production workflow.

**Consequences:** Operational docs treat AWS as dev/staging-like, not HA production.
