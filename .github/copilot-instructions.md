# Copilot instructions

Read `/project-context.xml` for full project context; its `<current_state>` section is the source of truth.
Conventions, structure, and ownership are in `.kiro/steering/` (`product.md`, `tech.md`, `structure.md`). Follow them.

Key rules:
- Response shapes are defined in `fixtures/sample_responses.json`; keep `api/app/models.py` and `web/src/lib/types.ts` in sync with it.
- Static zone data lives only in `fixtures/zones.json`; regenerate with `python simulator/build_fixtures.py`.
- Schema changes go in new files under `supabase/migrations/`.
- Never commit secrets. The browser only gets the Supabase anon key.
- Don't break stub mode (API and web must work with no env vars set).
