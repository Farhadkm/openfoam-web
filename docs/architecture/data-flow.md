# Data flow

## Job lifecycle

1. **Upload** — User POSTs case ZIP to backend.
2. **Persist metadata** — MongoDB record with job id and status.
3. **Extract** — ZIP → `/jobs/<job_id>/case/` on `jobs_data`.
4. **Run** — Backend calls runner `POST /internal/run` with shell commands.
5. **Execute** — Runner starts OpenFOAM container; stdout/stderr → `/jobs/<job_id>/openfoam.log`.
6. **Complete** — Backend updates status; UI lists outputs and VTK paths.
7. **Visualize** — Trame loads `case/VTK/`; UI syncs state via postMessage.
8. **AI (optional)** — Client sends `init` with page context; model may return XML to update form fields or viewer.

## AI message contract

Defined in `ai/prompt.py`, parsed in `frontend/lib/aiChat.ts`:

- `<UpdateInputs>` — simulation field JSON
- `<ViewerCmd>` — viewer actions (time, scalar, play, etc.)
- `<NeedMoreInfo>` / `<CasualMessage>` — conversational text

## Download path

Backend packages job workspace for ZIP download; same tree the runner and viewer use.
