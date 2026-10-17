---
inclusion: always
---
# Repo structure and ownership

| Path | Owner | What |
|---|---|---|
| `supabase/migrations/` | Andrew (data) | Schema, SQL functions, views, RLS |
| `supabase/seed.sql` | generated | From `fixtures/zones.json` via `simulator/build_fixtures.py` |
| `simulator/` | Andrew (data) | Synthetic session generator (`run.py`), demand model (`model.py`) |
| `fixtures/` | shared contract | `zones.json` (canonical static data), `zones.geojson`, `sample_responses.json` (API shapes) |
| `api/` | Teammate A (backend) | FastAPI app, tests, Dockerfile |
| `web/` | Teammate B (frontend) | Next.js app |
| `fly.toml` | Teammate A | Fly app: `app` (API) + `worker` (simulator) processes |
| `.github/workflows/` | Andrew | CI and deploy |

## Database tables (snake_case)
`operator`, `facility`, `zone`, `rate_rule`, `parking_session`, `destination`, `event`, `impacts`, `zone_status`
Views: `mv_hourly_occupancy`, `mv_dwell_turnover`
Functions: `walk_minutes()`, `refresh_zone_status()`, `refresh_analytics()`, `predict_availability(zone_id, at)`

## API routes
`GET /health`, `GET /zones`, `GET /status`, `GET /predict?zone&time`, `GET /opening-soon?lat&lng`,
`GET /recommend?destination&arrival`, `POST /demo/scenario {scenario: game_day|family_weekend|clear}`

## Web routes
`/` live map, `/plan`, `/insights`, `/demo`

## Git
Branches: `data/...`, `api/...`, `web/...`. Small PRs, squash merge, CI must pass. Tag the team on PRs touching `fixtures/` or `supabase/migrations/`.
