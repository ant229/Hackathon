---
inclusion: always
---
# Tech stack and conventions

## Stack
- **web/**: Next.js 16 (App Router, TypeScript), Tailwind, react-leaflet, Recharts, supabase-js. Deployed on Vercel.
  - This Next.js version has breaking changes; read `web/node_modules/next/dist/docs/` before using unfamiliar APIs (see `web/AGENTS.md`).
  - Leaflet must be client-only: `next/dynamic` with `ssr: false` inside a Client Component (see `web/src/components/LiveMap.tsx`).
  - Don't read `Date.now()` / `new Date()` during render in prerendered pages; do it in `useEffect` or handlers.
- **api/**: FastAPI + Pydantic v2, httpx to Supabase PostgREST. Deployed on Fly.io (region ewr) with the simulator as a second process.
- **supabase/**: Postgres + PostGIS. Schema only changes through SQL files in `supabase/migrations/`, never the dashboard.
- **simulator/**: Python, deterministic demand model in `model.py`.

## Rules
- **Let Postgres do analytics** (materialized views, SQL functions). Keep FastAPI thin. Keep the frontend simple.
- **Contracts**: response shapes live in `fixtures/sample_responses.json`, mirrored by `api/app/models.py` and `web/src/lib/types.ts`. Change all three together, and tell the team.
- **Static zone data** lives in `fixtures/zones.json` only. After editing it run `python simulator/build_fixtures.py` to regenerate `supabase/seed.sql` and `fixtures/zones.geojson`.
- **Stub mode**: with no `SUPABASE_URL`, the API returns the fixture shapes and the web app uses mock data. Never break stub mode.
- **Secrets**: service role key only in Fly secrets. The browser only ever gets the anon key (RLS is public read-only).
- Python: ruff (`ruff check api simulator`), pytest in `api/tests`. TypeScript: `npm run lint` and `npm run typecheck` in `web/`.
- Times are stored in UTC (timestamptz); display and hour-of-week analytics use America/New_York.
