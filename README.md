# South Side Parking

Where, when, and for how long parking opens up around Lehigh University and South Bethlehem.
Occupancy is estimated from pay-by-hour payment sessions (synthetic for the hackathon), shown on a live map,
with predictions, a "plan a visit" recommender, and analytics.

**Context for every AI tool (Kiro, Copilot, Claude): [`project-context.xml`](project-context.xml).**
Conventions: [`.kiro/steering/`](.kiro/steering/).

```
api/          FastAPI (Teammate A)          -> Fly.io
web/          Next.js (Teammate B)          -> Vercel
supabase/     migrations + seed (Andrew)    -> Supabase
simulator/    synthetic sessions (Andrew)   -> runs on Fly as the "worker" process
fixtures/     shared contracts: zones.json (canonical data), sample_responses.json (API shapes)
```

## Run locally (no accounts needed)

Everything works in **stub mode** with no env vars: the API returns `fixtures/sample_responses.json` and the web app uses mock data.

```bash
# API  -> http://localhost:8000/docs
cd api && pip install -r requirements-dev.txt && uvicorn app.main:app --reload

# Web  -> http://localhost:3000
cd web && npm install && npm run dev

# Simulator sanity check (no database)
python -m simulator.run --dry-run
```

Tests: `cd api && pytest` · `ruff check api simulator` · `cd web && npm run lint && npm run typecheck`

## One-time cloud setup (Andrew, ~30 min)

### 1. Supabase
1. Create a project at supabase.com (region **us-east-1**). Save the database password.
2. Dashboard > Database > Extensions: enable **postgis** and **pg_cron**.
3. Apply the schema and seed data:
   ```bash
   npx supabase login
   npx supabase link --project-ref <your-project-ref>
   npx supabase db push --include-seed
   ```
4. Project Settings > API: copy the **URL**, **anon key**, and **service_role key**.
5. In `.kiro/settings/mcp.json`, replace `YOUR_PROJECT_REF` so Kiro's Supabase MCP server can see the database.

### 2. Fly.io (API + simulator)
```bash
fly auth login
# edit fly.toml: set `app` to a unique name, then:
fly launch --no-deploy --copy-config
fly secrets set SUPABASE_URL=https://<ref>.supabase.co SUPABASE_SERVICE_ROLE_KEY=<service_role key>
fly deploy
fly scale count app=1 worker=1
```
The worker backfills 14 days of history on first start, then adds live sessions every minute.
Check: `curl https://<app>.fly.dev/health` should say `"mode":"live"`.

### 3. Vercel (web)
Import the GitHub repo, set **Root Directory = `web`**, and add env vars
`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL` (your fly.dev URL).
Every PR gets a preview URL.

### 4. GitHub secrets (Settings > Secrets and variables > Actions)
| Secret | Used by |
|---|---|
| `FLY_API_TOKEN` (`fly tokens create deploy`) | auto-deploy API on merge to main |
| `SUPABASE_ACCESS_TOKEN`, `SUPABASE_PROJECT_REF`, `SUPABASE_DB_PASSWORD` | auto-apply migrations on merge to main |

Workflows skip deploys politely until secrets are set; tests always run.

## Team workflow
- `main` always works. Branch per lane: `data/...`, `api/...`, `web/...`. PR every 1-3 hours, squash merge, CI must pass.
- Changing `fixtures/` or `supabase/migrations/` affects everyone: tag the team on the PR.
- Edit zone data in `fixtures/zones.json`, then run `python simulator/build_fixtures.py`.
- Tag `v0.1-mvp` around hour 12 and `v1.0-demo` at feature freeze.

## Data notes
Coordinates are approximate, and rates/limits marked `"verify": true` in `fixtures/zones.json` are placeholders.
Check bethpark.org and parking.lehigh.edu before the demo.
