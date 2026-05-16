# Development workflows

## Daily local loop

1. `docker compose up --build` (or `make up`)
2. Upload a test case ZIP from UI
3. Inspect job log and `case/VTK/` if visualization is needed
4. `docker compose logs -f <service>` for debugging

## Changing a service

1. Edit code under `frontend/`, `backend/`, etc.
2. Rebuild affected image: `docker compose up --build <service>`
3. If env or ports change, update `docker-compose.yml` and `docs/development/setup.md`

## Changing infrastructure (AWS dev)

1. Edit `deploy/aws/terraform/`
2. `terraform plan` / `apply`
3. Update GitHub secrets if outputs change
4. Push `dev` or re-run deploy workflow

## Documentation

When behavior or boundaries change, update:

- `docs/architecture/` for design impact
- Root `README.md` for user-facing run/troubleshoot steps
- `.cursor/rules/` if agent guidance should change
