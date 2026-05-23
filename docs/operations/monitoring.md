# Monitoring

## Local / dev

| Check | Command / URL |
|-------|----------------|
| Service status | `docker compose ps` |
| Logs | `docker compose logs -f bff` (or other service) |
| Backend health | `curl http://localhost:8000/health` |
| AI health | `http://localhost:8081/health` |
| MongoDB | `mongosh` to `127.0.0.1:27017` (host-mapped in Compose) |

## Distributed tracing and logs (OpenTelemetry + SigNoz)

Local Compose runs **SigNoz** (UI + ClickHouse + `signoz-otel-collector`) and a Forge **OpenTelemetry Collector** (`otel-collector`) that receives app traces and logs over OTLP and forwards them to SigNoz.

| Item | Value |
|------|--------|
| SigNoz UI | http://localhost:8080 |
| OTLP ingest (apps → Forge collector) | `http://otel-collector:4317` (gRPC) inside the Compose network |
| Forge collector config | `deploy/otel-collector-config.yaml` |
| SigNoz config / reference compose | `deploy/signoz/` (services merged into root `docker-compose.yml`) |
| App logging setup | `backend/shared/telemetry.py`, `backend/shared/request_logging.py` |

**Resource note:** SigNoz uses ClickHouse and ZooKeeper. Allocate **~4 GB RAM** to Docker Desktop (or the Docker daemon) for a stable local stack; first startup can take several minutes while ClickHouse migrates.

**First visit:** Open http://localhost:8080 (not port 3301) and complete the one-time setup wizard (org/user). Until the wizard is done, **Services**, **Hosts**, and some dashboards can look empty even though traces are already in ClickHouse.

After `docker compose up -d --build`, each backend container should log once at startup: `telemetry configured service=bff traces=on logs=on`. If that line is missing, rebuild backend images: `docker compose build bff simulation forge-runner ccs ics`.

**Collector note:** `signoz-otel-collector` runs without OpAMP in this stack so OTLP ingest works before SigNoz org setup (OpAMP would otherwise disable pipelines).

**Instrumented services:** `bff`, `simulation`, `forge-runner`, `ccs`, `ics`. The BFF uses httpx instrumentation so proxied calls to simulation/CCS appear as child spans. `trame-viewer` is not instrumented in v1.

**Quick check**

```bash
docker compose up -d --build
curl -s http://localhost:8000/health | jq .
```

Open SigNoz → **Services** → select `bff` → find a trace for `GET /health` with child spans to `simulation` and `ccs`. (Traces can also be opened from **Traces** with a `service.name = bff` filter.)

**View correlated logs on a trace**

1. Generate traffic: `curl -s http://localhost:8000/api/jobs` (health checks are not logged)
2. SigNoz → **Traces** → filter `service.name = bff` → open a `GET /health` trace.
3. In the trace waterfall, **click a span** (e.g. `GET /health` on `bff`, or a child span to `simulation` / `ccs`).
4. Open the **Logs** tab for that span — request/proxy lines emitted during that span appear here when log–trace correlation is working.

You can also start from **Logs** (filter `service.name = bff`) and use **View trace** on a line that has `trace_id`.

Minimal log events: HTTP request start/end (`forge.request`), BFF proxy target/status (`services.bff.proxy`), job lifecycle (`simulation`), `internal/run` (`forge-runner`), conversation/WebSocket connect (`ccs`), classify intent summary (`ics`). CCS WebSocket chat logs every inbound/outbound JSON frame with `conversation_id=` (see `backend/services/ccs/ws_logging.py`; truncation uses `LOG_HTTP_BODY_MAX`). Filter SigNoz logs: `conversation_id=<uuid>`. Stdout from `docker compose logs bff` includes `trace_id` / `span_id` on each line when OTEL is enabled.

**HTTP response body previews (local dev)**

| Env | Default (local Compose) | Effect |
|-----|-------------------------|--------|
| `LOG_HTTP_BODY_ENABLED` | `true` | When `false`, no body previews |
| `LOG_HTTP_BODY_MAX` | `1024` | Max characters in `body_preview=`; set `0` to disable |

Implementation: `backend/shared/http_body_logging.py`, used by `request_logging` middleware (each instrumented service) and BFF `proxy.py` for upstream responses.

Logged on small JSON/text responses: `body_preview=…` on `forge.request` and `proxy response … body_preview=…` on proxied routes. Skipped for HTTP body preview: WebSocket **proxies** (BFF does not log WS frames); CCS logs WS payloads directly on the service with `conversation_id`. Also skipped: `/viewer` assets, `multipart` / `application/octet-stream` / ZIP (logged as `[binary N bytes]` only), responses larger than 64 KiB (`[large N bytes]`). Obvious JSON secret fields and `Bearer` tokens are redacted; never log credential paths.

**Security:** treat previews as sensitive — dev-only. Disable on shared hosts: `LOG_HTTP_BODY_ENABLED=false` or `LOG_HTTP_BODY_MAX=0` (AWS dev overlay sets `LOG_HTTP_BODY_ENABLED=false`).

```bash
curl -s http://localhost:8000/api/jobs
docker compose logs bff 2>&1 | grep body_preview
```

In SigNoz: open a trace → click a span → **Logs** tab — `body_preview` lines appear on the same span as the request when log–trace correlation is enabled.

**Troubleshooting: empty Services, Hosts, or Logs**

| Symptom | Check |
|---------|--------|
| Empty **Services** / **Hosts** | Finish the wizard at http://localhost:8080; run `curl http://localhost:8000/health` several times; set SigNoz time range to **Last 15 minutes**. |
| No services in SigNoz | Wait for ClickHouse migrator; confirm `docker compose ps` shows `signoz-otel-collector` and `otel-collector` **healthy**. |
| Empty **Logs** explorer | Backend image likely predates OTLP log export — rebuild `bff simulation ccs ics forge-runner` and confirm startup `logs=on`. |
| Traces but no logs on span | Rebuild backend images after telemetry changes: `docker compose up -d --build bff simulation ccs ics forge-runner`. Confirm `OTEL_SDK_DISABLED` is unset. |
| Verify data landed | `docker compose exec signoz-clickhouse clickhouse-client -q "SELECT count() FROM signoz_traces.distributed_signoz_index_v3"` and `... signoz_logs.logs_v2` — counts should rise after health curls. |
| Logs in **Logs** explorer but not on trace | Log lines lack `trace_id` — usually middleware order (request logs must run inside the FastAPI span) or `LoggingInstrumentor` not active; see `backend/shared/telemetry.py`. |
| No OTLP logs at all | `deploy/otel-collector-config.yaml` must export `logs` to `signoz-otel-collector`; SigNoz collector needs a non-`nop` `logs` pipeline (`deploy/signoz/signoz-otel-collector-config.yaml`). |
| Debug locally | `docker compose logs bff 2>&1 \| tail -20` — lines should end with `trace_id=… span_id=…` for non-health requests (e.g. `GET /api/jobs`). |

Pipeline: app (OTLP logs + traces) → `otel-collector` → `signoz-otel-collector` → ClickHouse (`signoz_logs`, `signoz_traces`).

**Trace AI conversation turns (one message end-to-end)**

Each chat `user_message` creates a trace rooted at **`conversation.turn`** on service **`ccs`**, with child spans:

| Span | Service | Meaning |
|------|---------|---------|
| `conversation.turn` | ccs | Whole turn (user text → classify → agent → WS replies) |
| `conversation.classify` | ccs | Outbound call to ICS |
| `POST /classify` (HTTP) | ccs → ics | Auto from httpx + FastAPI instrumentation |
| `conversation.classify.model` | ics | Gemini intent classification |
| `conversation.agent` | ccs | Specialist agent (e.g. `parameter_configuration`) + Vertex reply |

Span attribute **`conversation.id`** matches the ID in the AI chat header (also in baggage for ICS).

**SigNoz — one conversation**

1. Send a message in the AI assistant; copy **conversation ID** from the panel.
2. **Traces** → filter: `service.name = ccs` and `span.name = conversation.turn` (or search attribute `conversation.id = <uuid>` if your SigNoz version indexes it).
3. Open the trace → waterfall should show `conversation.classify` → HTTP to `ics` → `conversation.classify.model`, then `conversation.agent`.
4. Click each span → **Logs** tab for correlated `ws inbound/outbound` events and `forge.request` lines (when emitted inside the span).
5. Span **Events**: `conversation.ws.inbound`, `conversation.ws.outbound`, `conversation.classify.result`, `conversation.agent.reply` (payload previews truncated by `LOG_HTTP_BODY_MAX`).

Implementation: `backend/shared/conversation_tracing.py`, wired in `backend/services/ccs/app.py` and `backend/services/ics/`.

**Trace a real user flow**

1. Start the stack (`docker compose up -d --build`).
2. Create a job from the UI or API, e.g. `POST http://localhost:8000/api/jobs` (multipart ZIP + commands) via the frontend or `curl`.
3. In SigNoz, filter service `bff` or `simulation` for `POST /api/jobs` (and later `POST /internal/run` on `forge-runner` when the job runs).

**Disable tracing and OTLP logs locally**

Set `OTEL_SDK_DISABLED=true` on backend services (see `.env.example`). This disables trace export and OTLP log export; stdout logging with `forge.request` middleware remains at `LOG_LEVEL` (default `INFO`).

## AWS dev EC2

Tracing is **disabled** in `docker-compose.aws-dev.yml` (`OTEL_SDK_DISABLED=true`) because no collector/SigNoz stack is deployed on the instance. Re-enable only after adding collector + SigNoz (or a hosted OTLP backend) to that environment.

- **SSM session:** `aws ssm start-session --target <instance-id>`
- On host: `docker compose -f docker-compose.aws-dev.yml ps` and `docker logs`
- GitHub Actions: deploy workflow run history for build/push failures

## Signals to watch

- Job stuck in running — runner or solver container exit code; read `forge.log`
- Viewer disconnect — large VTK payloads, `TRAME_WS_MAX_MSG_SIZE`, client refresh
- AI errors — Vertex credentials, `GOOGLE_CLOUD_PROJECT_ID`, quota
