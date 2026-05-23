# System overview

## Purpose

Allow users to upload an CFD case archive, run solver/mesh commands in a containerized environment, and visualize `case/VTK/` output in the browser with an optional AI copilot for parameters and viewer commands.

## Runtime topology

All application containers attach to the same Docker network. Job directories are stored under `/jobs/<job_id>/` on the `jobs_data` volume so the simulation service, runner, ephemeral solver job container, and Trame viewer read identical files.

The runner is the only service with access to `/var/run/docker.sock`. It creates short-lived solver containers that mount the same named volume (via `JOBS_VOLUME_NAME` / host volume name) so solver output lands where the API and viewer expect it.

## External systems

- **Vertex AI (Gemini)** — AI service; credentials via service account JSON
- **AWS (dev)** — single EC2 host running the same Compose topology with images from ECR

## Non-goals (current repo)

- Multi-tenant production hosting
- Kubernetes / serverless orchestration
- Automated mesh/solver validation beyond user-provided commands
