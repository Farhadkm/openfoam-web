# Coding standards

Project-specific Cursor rules: `.cursor/rules/30-code-standards.mdc`.

## Summary

- **Small, focused changes** aligned with each service’s existing patterns
- **Configuration via environment variables** — document new vars in setup and `.env.example`
- **Frontend:** extend `trameBridge.ts` and `aiChat.ts` for viewer/AI integration
- **Backend/runner:** keep job paths under `JOBS_ROOT`; do not hardcode volume names outside Compose/env
- **AI:** keep XML tag contract in `backend/services/ccs/prompt.py` in sync with `frontend/lib/aiChat.ts`

## API changes

Update OpenAPI consumers (frontend fetch calls) and mention breaking changes in PR description.
