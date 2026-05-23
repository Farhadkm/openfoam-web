# Data flow

## Job lifecycle

1. **Upload** — User POSTs case ZIP via BFF to simulation service.
2. **Persist metadata** — MongoDB record with job id and status.
3. **Extract** — ZIP → `/jobs/<job_id>/case/` on `jobs_data`.
4. **Run** — Simulation service calls runner `POST /internal/run` with shell commands.
5. **Execute** — Runner starts solver container; stdout/stderr → `/jobs/<job_id>/forge.log`.
6. **Complete** — Simulation service updates status; UI lists outputs and VTK paths.
7. **Visualize** — Trame loads `case/VTK/`; UI syncs state via postMessage.
8. **AI (optional)** — Client sends `init` with page context; model may return XML to update form fields or viewer.
9. **AI troubleshoot (optional)** — From job/run log UI, client POSTs log + template context to BFF `POST /api/ai/troubleshoot` → CCS one-shot Gemini guide (no ICS).

## AI message contract

Defined in `backend/services/ccs/prompt.py`, parsed in `frontend/lib/aiChat.ts`:

- `<UpdateInputs>` — simulation field JSON
- `<ViewerCmd>` — viewer actions (time, scalar, play, etc.)
- `<NeedMoreInfo>` / `<CasualMessage>` — conversational text

## Download path

Simulation service packages job workspace for ZIP download; same tree the runner and viewer use.
