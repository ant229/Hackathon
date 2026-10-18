# Implementation Plan: SpotStack (parking-monitor)

## Overview

This plan builds the full SpotStack MVP described in design.md. It covers the seed fixture, the FastAPI service (data model, simulator, prediction, associative engine, SSE stream, and routes), the Next.js web app (Home, Map, Plan, Explore, and Demo), and the project docs. The API is Python 3.13 and the web app is TypeScript.

Hard constraints. Every task follows these:

- **Local build at the workspace root** `/Users/andrewtakach/Hackathon 1`, in `fixtures/`, `api/`, `web/`, `docs/`, `README.md`, and `.env.example`. The draft code already in `fixtures/`, `api/`, and `web/` is replaced or extended in place to match design.md. The tasks that replace legacy pieces also remove them: the `/insights` route and page, `web/lib/usePoll.ts`, `web/lib/occupancy.ts`, `api/tests/test_core.py`, and `web/.env.example`.
- **No git commands of any kind.** That includes add, commit, branch, push, stash, checkout, restore, reset, and clean.
- **`claude output/` is read-only reference material** for the deferred deploy phase. Never write to it, and never import, run, or copy build artifacts from it.
- **API toolchain:** Python 3.13 via uv in `api/`, with exact `==` pins for fastapi, uvicorn, and numpy, and a dev group with pytest, httpx, and hypothesis. No ML library anywhere.
- **Web toolchain:** Next.js 16.4.2 (App Router), React 19, TypeScript, Leaflet 1.9.4, and ESLint 9 flat config with eslint-config-next 16.4.2. Use exact versions (no `^` or `~`), and no chart or UI component library.
- **Frontend design:** all frontend UI work applies the apple-design-skill at `/Users/andrewtakach/Hackathon 1/apple-design-skill`. Read `SKILL.md`, then the always-load set, then the screen-specific files each task names. The always-load set is `references/hig/accessibility.md`, `layout.md`, `typography.md`, `color.md`, `designing-for-ios.md`, `designing-for-macos.md`, and `references/cross-platform.md`. SpotStack is a web app, so the skill's principles and foundations apply, and native conventions apply only where the web has an equivalent.
- **Styles:** only `web/app/globals.css` holds shared tokens and base styles. Task 7.2 creates it, and only 7.5 and 14.3 may adjust it later, in waves where no other task touches it. Every page and component keeps its styles in its own CSS module, for example `web/app/map/page.module.css`, so parallel tasks never edit the same stylesheet.
- **No authentication in the local build,** including on `POST /demo/scenario`. uvicorn binds `127.0.0.1`, and access control is required before any deployment.
- **Long-running processes** (uvicorn, `npm run dev`) start only as background processes during verification, and are stopped afterwards.

| Purpose | Directory | Command |
|---|---|---|
| Regenerate the seed | workspace root | `python3 fixtures/build_seed.py` |
| Start the API | `api/` | `uv run uvicorn app.main:create_app --factory --port 8000` |
| Start the web app | `web/` | `npm run dev` |
| API tests | `api/` | `uv run pytest` |
| Web checks | `web/` | `npm run check` (`tsc --noEmit && eslint . && node scripts/check-contrast.mjs`) |

Parallelism: the API work (tasks 1–5) and the web foundation (task 7) start together in wave 0. The web app builds against the API contract in design.md, so it doesn't wait for the API. The page tasks (8–12) and docs (13) run in parallel once the web foundation is done. The dependency graph at the end lists every wave.

## Tasks

- [x] 1. Build the seed fixture
  - [x] 1.1 Rewrite `fixtures/build_seed.py` and regenerate `fixtures/seed.json`
    - Work at the workspace root, replacing the draft generator in place. Use only the standard library and run `python3 fixtures/build_seed.py`. No git.
    - Write one JSON document with keys `operators`, `facilities`, `zones`, `rate_rules`, `destinations`, `event_templates`, `demand_curves`, `profiles`, and `scenarios`. Use the design's formats: `"HH:MM"` local times, `"24:00"` for end of day, and `day_of_week` 0 = Monday.
    - Operators: BPA with `pay_app` ParkMobile and PayByPhone, and Lehigh Parking Services with Passport Parking.
    - Facilities and the 15 zones from the design's zone catalog, with capacity, `visitor_allowed`, profile, and note:
      - BPA on-street zones get the pay-station note.
      - Farrington gets the Text2Park note (after 16:00 and on weekends).
      - Zoellner Levels 2–4 get "Permit holders only. Visitors use Level 1."
    - Rate rules per the catalog:
      - RapidPark (Main St, E 3rd West/East, E 4th): $2.50 and 120 min, Mon–Sat 08:00–21:00.
      - FlexPark (New St, Morton): $1.50 and 180 min, Mon–Sat 08:00–21:00.
      - Polk Street and New Street garages: $1.00, no limit, daily 06:00–24:00.
      - Zoellner Level 1: $1.00, no limit, daily 07:00–23:00.
      - Zoellner Levels 2–4: $0 permit rule, Mon–Fri 07:00–17:00.
      - Farrington: $1.00, no limit, daily 06:00–24:00.
      - Packer Ave and Alumni Level 1 meters: $1.00 and 120 min, Mon–Fri 07:00–17:00.
    - Set `placeholder` per the catalog, and give every rule with `placeholder: false` a `source` string.
    - Four destinations with lat/lng: Zoellner Arts Center, Goodman Stadium, Alumni Memorial Building, and 3rd Street shops.
    - Event templates for football, Zoellner performances, and Family Weekend, each with a schedule rule, expected attendance, and per-zone impacts (all ≥ 1.0). Add the `game_day` and `family_weekend` scenarios (45 min each).
    - The profiles table and a 168-value demand curve per zone that follow the design's three shaping rules:
      - Unenforced hours are 0.0, except the first hour after enforcement, which is 0.1 × the previous hour.
      - The first enforced hour is ≤ 0.40.
      - Consecutive enforced hours differ by ≤ 0.15.
    - Output is byte-for-byte deterministic (fixed key order and rounding).
    - _Requirements: 1.11, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.16, 3.7, 3.9, 3.10, 3.11, 4.7_

- [x] 2. Build the API foundation: toolchain, data model, geometry, and events
  - [x] 2.1 Pin the Python toolchain and dependencies in `api/`
    - In `api/pyproject.toml`, set `requires-python = "==3.13.*"` and pin fastapi, uvicorn, and numpy with `==`. Add a dev group with pytest, httpx, and hypothesis, also pinned with `==`. Keep the existing pins where they resolve on 3.13, and pin numpy and hypothesis to current releases. Keep `testpaths = ["tests"]`.
    - Add `api/.python-version` containing `3.13`.
    - Delete the legacy `api/tests/test_core.py`, which targets draft code that is being replaced.
    - Run `uv sync` in `api/`, which updates `uv.lock`. No git.
    - _Requirements: 6.6, 20.1, 20.8_

  - [x] 2.2 Implement `api/app/data.py`
    - Replace the draft module in place. Expect `main.py` and `sim.py` to stay broken until tasks 3.1 and 5.2 rewrite them.
    - Define dataclasses for the nine tables with the design's columns, and no plate column anywhere. `DataStore` holds them in dicts keyed by primary key.
    - `load_seed(path)` parses `"HH:MM"` into minutes, builds every table, and creates one Zone_Status row per zone. It then calls `validate()`, which fails fast and names the offending key for any of these: a dangling FK, a duplicate Impacts PK, a missing or duplicate Zone_Status, capacity ≤ 0, or a boost < 1.0.
    - Add the helpers:
      - `TZ = ZoneInfo("America/New_York")`
      - `hour_of_week(ts)`: rejects naive datetimes; Monday = 0
      - `haversine_m` with R = 6 371 008.8 m
      - `walk_minutes = ceil(d × 1.3 / 80)`
      - `applicable_rule(store, zone_id, ts)`: day match and `start ≤ local minute < end`
      - `is_time_limited(store, zone_id, ts)`
    - The local table names map 1:1 to the scaffold in `claude output/Hackathon`, which is a read-only reference.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 8.4, 9.4, 16.1_

  - [x] 2.3 Implement `api/app/events.py`
    - `expand_events(templates, today, history_start, horizon_days=28)` returns `(events, impacts)` covering `[history_start, today + 28 days]`.
    - Football runs Saturdays 12:00–16:00 on the anchor ± 14k days, where the anchor is the first Saturday on or after `today`.
    - Zoellner performances run every Friday and Saturday, 19:30–22:00.
    - Exactly one Family Weekend runs from Saturday 09:00 at anchor + 7 days through Sunday 17:00.
    - Build times in local time so they're correct across DST. Use deterministic IDs such as `football-2026-11-07`, and create one Impacts row per template zone carrying the template's boost.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x]* 2.4 Write property test for hour-of-week in `api/tests/test_prop_time.py`
    - **Property 1: Hour-of-week follows America/New_York local time**
    - Generate aware datetimes in several zones, including dates across DST transitions.
    - **Validates: Requirements 1.13**

  - [x]* 2.5 Write property test for distance and walk minutes in `api/tests/test_prop_geo.py`
    - **Property 2: Distance and walk minutes follow the formula**
    - Check that `haversine_m` is non-negative, symmetric, and zero for identical points, and that `walk_minutes` matches the formula. Task 5.5 asserts that endpoints report consistent values.
    - **Validates: Requirements 8.4, 9.4**

  - [x]* 2.6 Write seed-content example tests in `api/tests/test_seed.py`
    - Check the operators and pay apps, the RapidPark and FlexPark rules, the BPA notes, Polk capacity 731, New Street Garage, Zoellner Levels 1–4, Farrington (capacity 52, hours, note), the Packer and Alumni meters, the placeholder and source flags, the four destinations, 168-value curves for every zone, and template boosts ≥ 1.0.
    - _Requirements: 1.11, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.16, 4.7_

  - [x]* 2.7 Write property test for event expansion in `api/tests/test_prop_events.py`
    - **Property 8: Event templates expand on schedule relative to the start date**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

- [ ] 3. Implement the simulator in `api/app/sim.py`
  - [x] 3.1 Implement simulator core, history generation, live advance, and Zone_Status
    - Replace the draft `sim.py` in place. Add `Simulator(store, *, start, history_days=28, rng_seed=7, step_min=5)`, with all randomness drawn from `numpy.random.default_rng(rng_seed)`.
    - Add a `build_simulator(seed_path, *, start, history_days, rng_seed)` helper. It loads the seed, expands events relative to `start`'s local date, and constructs the Simulator. Both `create_app` and the test fixtures use it.
    - `generate_history()` steps through `[start − history_days, start)` in 5-minute steps, running the design's arrival controller in each:
      - expire sessions, then skip the zone when no rule applies
      - `target = min(0.98, curve × boost)`
      - known departures, `gain`, and a Poisson draw
      - cap arrivals at free capacity
      - place each start uniformly inside the step and before the rule ends
    - Draw the paid duration using the design's five steps (15-minute multiples, limit cap, enforcement-end cap, 15-minute floor).
    - Draw End_Time from the departure table: Left Early 0.25, On Time 0.63, Overstayed 0.12.
    - `event_boost(zone_id, t)` returns `(boost, event)` over Boost_Windows `[start − 2 h, end + 1 h]`, or over `window_override` when it's set. `Event_ID` is the event supplying the max boost at the session's start when that boost is > 1.0. Ties go to the highest boost, then the earliest start.
    - Keep these internals:
      - integer session keys
      - per-zone end-time heaps
      - an append-only change log of session keys whose `end_time` changed
      - `add_listener(fn(new_keys, changed_keys))`
    - `advance_to(now)` runs the controller over `[last, now)` (about 2 s live), then recomputes every Zone_Status row:
      - `occupied` = `active / capacity`
      - `active_sessions` = the active count
      - `opening_soon` = active sessions with `t ≤ paid_until ≤ t + 15 min` when the zone is time-limited, otherwise 0
      - `updated_at` = `t`

      It returns only the rows whose published values changed. `zone_status()` returns every row.
    - Create `api/tests/conftest.py` with three fixtures:
      - `fake_clock`: a mutable aware time, a weekday afternoon in America/New_York
      - `make_sim`: a factory for 2–3-day simulators on a zone subset
      - `default_sim`: session-scoped, full seed, 28 days, seed 7

      Later test files define their own API client fixtures locally, so no other task edits conftest.py.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.12, 3.13, 3.14, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.3, 20.4_

  - [x] 3.2 Implement baselines, prediction, and opening-soon counts
    - In each history step, record an occupancy sample into `(sum, count)[zone][hour_of_week]`. Skip samples that fall inside the Boost_Window of any event impacting the zone.
    - After history, compute the baselines once as numpy arrays, using 0.0 when a slot has no samples.
    - Add `baseline(zone_id, how)`, and `predict(zone_id, t) -> Prediction` with the baseline, boost, event, `predicted_occupancy = min(1, baseline × boost)`, and `predicted_availability = 1 − predicted_occupancy`.
    - `opening_soon_counts(t)` returns, for each time-limited zone, the count of active sessions with `paid_until` in `[t, t + 15 min]`.
    - Use plain arithmetic and numpy array math only, with no ML imports.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.1_

  - [x] 3.3 Implement scenarios, expiry, and reset
    - `apply_scenario(name, now) -> ScenarioResult` runs synchronously:
      - Reject any name outside `game_day`, `family_weekend`, `reset` with `UnknownScenario(allowed)`.
      - End any active scenario: set End_Time = `now` on its still-active injected sessions (logged as changed), end its event at `now`, and deactivate it. `reset` stops here and reports before and after occupancy for the zones that held injected sessions.
      - Create the live Event "Game Day (Live Demo)" or "Family Weekend (Live Demo)", running from `now` to `now + 45 min` with `window_override = [trigger, expires_at]` and Impacts copied from the template.
      - Handle each impacted zone in one of three ways:
        - Not enforced: `skipped_reason "not_enforced"`.
        - `before ≥ 0.95`: `"already_full"`.
        - Otherwise inject `target_count − active` sessions, using the design's `predicted`, `target`, and `target_count` formulas and never exceeding capacity.
      - Each injected session starts at `U(max(now − 10 min, rule start), now)`, carries the live Event_ID, and has `injected=True`. Its paid duration follows the normal rules with a 45-minute floor that still respects the limit, and its outcome is On Time (0.84) or Overstayed (0.16).
      - Recompute Zone_Status, notify listeners, and return the event plus, per affected zone, `zone_id`, `zone_name`, `occupied_before`, `occupied_after`, `boost`, and `skipped_reason`.
    - `scenario_status(now) -> ActiveScenario | None` includes `minutes_remaining`. `advance_to` deactivates the scenario once `now ≥ expires_at`.
    - _Requirements: 13.2, 13.3, 13.4, 13.5, 13.6, 13.9, 13.10, 13.11_

  - [x]* 3.4 Write property test for session rules and capacity in `api/tests/test_prop_sim_rules.py`
    - **Property 3: Generated sessions obey payment rules and capacity**
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.8, 3.12**

  - [x]* 3.5 Write property test for determinism in `api/tests/test_prop_sim_determinism.py`
    - **Property 4: Simulation is deterministic for a fixed seed**
    - **Validates: Requirements 3.14**

  - [x] 3.6 Write property test for Zone_Status in `api/tests/test_prop_zone_status.py`
    - **Property 5: Zone_Status matches a brute-force recount**
    - Required. This test protects the live map numbers. Use a naive Python loop over all sessions as the oracle, at generated evaluation times after `advance_to`.
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

  - [x]* 3.7 Write property test for baseline exclusion in `api/tests/test_prop_baseline.py`
    - **Property 6: Baseline excludes boosted samples**
    - Use a reference mean over the recorded samples outside every impacting Boost_Window.
    - **Validates: Requirements 6.1, 6.2**

  - [x] 3.8 Write property test for scenario injection in `api/tests/test_prop_scenario_injection.py`
    - **Property 19: Scenario injection reaches its target**
    - Required. This test protects the Game Day demo moment.
    - **Validates: Requirements 13.2, 13.3, 13.4, 13.5, 13.6**

  - [ ]* 3.9 Write property test for scenario lifecycle in `api/tests/test_prop_scenario_lifecycle.py`
    - **Property 20: Scenario lifecycle keeps at most one scenario active**
    - **Validates: Requirements 13.9, 13.10, 13.11**

  - [ ] 3.10 Write calibration and history-budget tests in `api/tests/test_calibration.py`
    - Required. These tests protect the demo. They use the session-scoped `default_sim` (28 days, seed 7) and check:
      - History spans ≥ 28 days and ends at `start`.
      - The Left Early share is in [0.15, 0.40], and the Overstayed share is in [0.05, 0.20], using the 5-minute Outcome tolerance.
      - Per zone and hour-of-week, the mean occupancy outside Boost_Windows is within 0.10 of the curve.
      - Main St and E 3rd St average ≥ 0.85 from 10:00 to 18:00, Mon–Sat.
      - Main and 3rd St turnover is below the BPA on-street median.
      - Morton averages ≤ 0.40 during enforcement.
      - `generate_history()` finishes in under 15 s.
    - If a check fails, tune the profile parameters in `fixtures/build_seed.py` (then regenerate `seed.json`) or the controller constants in `sim.py`. Never loosen a tolerance.
    - _Requirements: 3.1, 3.5, 3.6, 3.7, 3.9, 3.10, 3.11, 20.5_

- [ ] 4. Implement the session source and associative engine
  - [x] 4.1 Implement `api/app/sources.py`
    - A frozen `SessionRecord` with exactly `zone_id`, `start_time`, `paid_until`, `end_time`, and `event_id`.
    - A `SessionSource` Protocol with `sessions_since(cursor)` and `changed_since(cursor)`, each returning `(list[(key, record)], new_cursor)`.
    - `SimulatorSource(sim)`, backed by the simulator's session list and change log.
    - Keys are opaque and never leave the API. A docstring states that adapters must drop plates and personal identifiers before building records.
    - _Requirements: 18.1, 18.2, 18.3, 18.4_

  - [x] 4.2 Implement the engine model, load, sync, and evaluate in `api/app/associative.py`
    - Define FIELDS in display order, with the derivations from the design table: Zone, Facility Type, Operator, Pay App, Visitor Access, Day, Arrival Hour, Time of Week, Event, Stay Length, Outcome, and Time Limit.
    - Keep these structures:
      - `symbols[f]` in insertion order, with `pos[f]` mapping value to index
      - `cols[f]` in the narrowest unsigned dtype (`uint8`, `uint16`, or `uint32`), with capacity doubling and a dtype upgrade on overflow
      - the hidden measures `stay_min`, `paid_hours`, `revenue` (float32), `slot` (uint8), and `cap_by_zone`
      - `key_to_row`
    - `load(source)` builds the model. `sync()` appends `sessions_since` rows, rewrites `changed_since` rows, and adds new symbols, so "Game Day (Live Demo)" shows up. An `RLock` guards `sync`, `evaluate`, and `select`.
    - `evaluate(selection)` follows the design:
      - normalize by dropping empty lists
      - build LUT masks and the associated rows
      - compute each Field_Context
      - run one `bincount` per field
      - classify the five states with `state(...)`
      - report counts from the context for fields with a selection, and from the associated rows otherwise
    - Apply display order at response time: Day runs Monday to Sunday, Arrival Hour 0 to 23, and Stay Length and Time of Week in bucket order. Other fields are alphabetical, with No Event last.
    - Raise `UnknownField` and `UnknownValue`. `model()` returns the fields with their values, `row_count`, and `history_days`.
    - Create `api/tests/engine_support.py` with an in-memory `ListSource` and a hypothesis strategy for `SessionRecord` lists over the seed zones.
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 10.11, 10.12, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 15.17, 18.1, 19.6_

  - [x] 4.3 Implement select, KPIs, heatmap, and charts in `api/app/associative.py`
    - `select(sel, field, value)` follows the click table:
      - Selected or Selected_Excluded: remove the value.
      - Possible or Alternative: add the value.
      - Excluded: set the field to `{value}` and drop the fields that share no row with it. If the selection still matches zero rows, keep only `{field: [value]}`.
    - The Result holds the selection, every field's values with state and count, and the KPIs: `sessions`, `avg_stay_min`, `revenue`, `overstay_rate`, and `avg_occupancy` (Little's law, clamped to 1). Every KPI except `sessions` is null when nothing matches.
    - The Result also holds the 7×24 heatmap (cells clamped to 1, null where a slot has no rows), `sessions_by_zone` in descending order, all five `stay_length` buckets, and `turnover` per zone with `avg_stay_min`.
    - Only counts, sums, averages, values, and states leave the engine. Each query does one LUT gather and one `bincount` per field.
    - _Requirements: 11.9, 11.10, 11.11, 11.12, 11.21, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 16.3_

  - [ ]* 4.4 Write property test for symbol-table encoding in `api/tests/test_prop_engine_encoding.py`
    - **Property 12: Symbol-table encoding round-trips every session**
    - **Validates: Requirements 10.1, 10.2, 10.3**

  - [ ]* 4.5 Write property test for field derivations in `api/tests/test_prop_engine_fields.py`
    - **Property 13: Field derivations classify every session exactly once**
    - **Validates: Requirements 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 10.11**

  - [ ] 4.6 Write property test for selection evaluation in `api/tests/test_prop_engine_states.py`
    - **Property 14: Selection evaluation matches the reference definitions**
    - Required. This test protects Explore. The oracle is a brute-force filter (OR within a field, AND across fields) plus a naive five-state classifier.
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7**

  - [ ]* 4.7 Write property test for toggle round trip in `api/tests/test_prop_engine_toggle.py`
    - **Property 15: Toggling a value is a round trip**
    - **Validates: Requirements 11.9, 11.10**

  - [ ]* 4.8 Write property test for excluded clicks in `api/tests/test_prop_engine_excluded.py`
    - **Property 16: Clicking an excluded value yields a consistent selection**
    - **Validates: Requirements 11.11, 11.12**

  - [ ]* 4.9 Write property test for KPIs and charts in `api/tests/test_prop_engine_kpis.py`
    - **Property 17: KPIs, heatmap, and charts match brute-force aggregates**
    - **Validates: Requirements 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 15.12**

  - [ ]* 4.10 Write property test for incremental sync in `api/tests/test_prop_engine_sync.py`
    - **Property 18: Incremental sync equals a fresh build**
    - Generate sequences of `advance_to`, scenario triggers, and resets on a small simulator.
    - **Validates: Requirements 10.12, 19.6**

  - [ ] 4.11 Write the engine performance test in `api/tests/test_engine_perf.py`
    - Required. This test protects Explore's responsiveness. Build an engine over 100,000 synthetic rows and assert that the median of 5 `evaluate` calls is under 300 ms. The calls use a 2–3-field selection and return the full Result (states, KPIs, heatmap, and charts).
    - _Requirements: 11.21_

- [ ] 5. Implement the Broadcaster and the API routes
  - [x] 5.1 Implement `api/app/stream.py`
    - `Broadcaster` with `subscribe() -> asyncio.Queue` (maxsize 100), `unsubscribe(q)`, and a thread-safe `publish(rows)` that uses `loop.call_soon_threadsafe`. When a slow client's queue is full, clear it and enqueue a snapshot marker.
    - An async `event_stream(...)` generator:
      - sends `event: snapshot` with every row, then `event: status` with only the changed rows
      - sends `: heartbeat` after `heartbeat_s` seconds without an event (default 15)
      - stops when the client disconnects, or after `max_events`
    - _Requirements: 13.8, 15.2, 15.3, 15.4, 15.5_

  - [x] 5.2 Implement the `create_app` factory, lifespan, ticker, errors, and read endpoints in `api/app/main.py`
    - Replace the draft module-level app with `create_app(sim=None, clock=None, run_ticker=True)`. Remove the legacy `/insights` route and the draft globals.
    - Read env config:
      - `SEED_PATH`, default `../fixtures/seed.json`
      - `SIM_RNG_SEED`, default 7
      - `HISTORY_DAYS`, default 28
      - `CORS_ORIGINS`, default `http://localhost:3000`
    - The lifespan runs the design's five steps: load and validate, expand events, `generate_history`, `engine.load(SimulatorSource)`, and the ticker. Every 2 s the ticker runs `asyncio.to_thread(sim.advance_to, clock())`, publishes the changed rows, and calls `engine.sync()`. Ticker exceptions are logged, and the next tick retries.
    - Add an overridable `app.state.heartbeat_s` (default 15) for tests.
    - Error handling:
      - A `RequestValidationError` handler maps pydantic `missing` errors to 422 `missing_parameter` and all other validation errors to 422 `invalid_parameter`, with `parameter = loc[-1]`.
      - Unknown zone or destination IDs return 404 `not_found` with the ID in the message.
      - Error messages state the fix.
    - Routes: `/health`, `/zones`, `/destinations`, the async `/stream` (with `max_events`, `text/event-stream`, `Cache-Control: no-cache`, and `X-Accel-Buffering: no`), `/predict`, `/opening-soon`, and `/recommend`. Response shapes follow the design contract.
      - `/predict` and `/recommend` read naive times as America/New_York.
      - `/opening-soon` parses `near` strictly.
      - `/recommend` follows the five candidate and scoring steps. It accepts `limit` from 1 to 20 (default 5), reports `0`, `null`, and `false` when no rule applies, and adds `event_warning` when the boost is > 1.0.
    - Routes are sync `def`, except `/stream`. CORS allows `CORS_ORIGINS`. No response carries `session_id`, plates, or row-level sessions. There's no auth in the local build, and uvicorn binds `127.0.0.1`.
    - _Requirements: 3.13, 5.6, 6.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13, 9.15, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9, 15.14, 15.15, 15.16, 15.18, 16.2, 20.1, 20.3, 20.4_

  - [x] 5.3 Implement the demo and explore endpoints in `api/app/main.py`
    - `POST /demo/scenario` takes `{"scenario": str}`, typed as `str` so unknown names reach the 400 path. An unknown name returns 400 `unknown_scenario` with `allowed`.
    - A valid scenario applies synchronously. The route then publishes the changed Zone_Status rows to the Broadcaster and calls `engine.sync()` before it returns the ScenarioResult.
    - `GET /demo/status` returns `{"active": ...}` or `{"active": null}`.
    - Add `GET /explore/model`, `POST /explore/query`, and `POST /explore/select`. `UnknownField` and `UnknownValue` return 422 `invalid_parameter` naming the field or value, and a malformed selection returns 422 `invalid_parameter`.
    - Responses carry aggregates only. No auth on the demo endpoint in the local build.
    - _Requirements: 13.6, 13.8, 13.12, 15.10, 15.11, 15.12, 15.13, 15.17, 16.2, 16.3, 19.6_

  - [ ]* 5.4 Write property test for prediction in `api/tests/test_prop_predict.py`
    - **Property 7: Prediction is baseline times the maximum boost, clamped**
    - Cover both `sim.predict` and `/predict`, through `create_app(sim=small, clock=fake, run_ticker=False)`.
    - **Validates: Requirements 6.3, 6.4, 6.5, 6.7, 15.7**

  - [ ]* 5.5 Write property test for opening soon in `api/tests/test_prop_opening_soon.py`
    - **Property 9: Opening-soon results are filtered, counted, and distance-ranked**
    - Also assert that `walk_minutes` is consistent with `distance_m` (Property 2, endpoint half).
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 15.8**

  - [ ]* 5.6 Write property test for recommendation candidates in `api/tests/test_prop_recommend_candidates.py`
    - **Property 10: Recommendation candidates respect visitor access and the walk cutoff**
    - **Validates: Requirements 9.3, 9.5, 9.6, 15.9**

  - [ ]* 5.7 Write property test for recommendation scoring in `api/tests/test_prop_recommend_scoring.py`
    - **Property 11: Recommendation scoring, ordering, and fields are consistent**
    - **Validates: Requirements 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13**

  - [ ]* 5.8 Write property test for privacy in `api/tests/test_prop_privacy.py`
    - **Property 21: Responses expose aggregates only**
    - Walk every JSON response from every endpoint, looking for forbidden keys and lists of row-level records.
    - **Validates: Requirements 16.2, 16.3**

  - [ ] 5.9 Write property test for the error contract in `api/tests/test_prop_errors.py`
    - **Property 22: Errors follow one contract**
    - Required. This test protects the frontend's error messages. Generate missing parameters, malformed `near`, `time`, `arrival`, and `limit` values, unknown fields and values, unknown zone and destination IDs, and unknown scenario names.
    - **Validates: Requirements 8.6, 9.15, 13.12, 15.14, 15.15, 15.16, 15.17**

  - [ ]* 5.10 Write SSE and endpoint example tests in `api/tests/test_api_examples.py`
    - `/stream?max_events=2` checks the content type and headers, a full `snapshot`, and a `status` event after a forced change or scenario. A heartbeat test sets a short `app.state.heartbeat_s`.
    - Shape checks for `/zones`, `/destinations`, `/demo/status`, `/explore/model`, and `/explore/select`, plus a CORS preflight from `http://localhost:3000`.
    - _Requirements: 13.8, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.10, 15.11, 15.12, 15.13, 15.18_

  - [ ] 5.11 Write startup and smoke tests in `api/tests/test_smoke.py`
    - Required. These tests protect the demo.
    - With the default seed and 28 days, `create_app(run_ticker=False)` completes lifespan startup inside a `TestClient` context in under 30 s, and `/health` returns `status: ok` with 15 zones.
    - No table dataclass has a plate field.
    - `pyproject.toml` and `uv.lock` contain no ML package, and `app/` imports none of sklearn, torch, tensorflow, statsmodels, xgboost, or lightgbm.
    - _Requirements: 6.6, 16.1, 20.4, 20.5_

- [ ] 6. Checkpoint: API complete
  - Run `uv run pytest` in `api/`.
  - Start the API as a background process from `api/` with `uv run uvicorn app.main:create_app --factory --port 8000`. Curl `/health`, `/zones`, and `/explore/model` and confirm the shapes match design.md, then stop the process. No git.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Build the web foundation
  - [x] 7.1 Pin web dependencies, configure ESLint, and clear legacy pages
    - In `web/package.json`, use exact versions: next 16.4.2, react and react-dom 19 (keep 19.3.1), and leaflet 1.9.4. Dev dependencies: typescript, `@types/*`, eslint 9.x, and eslint-config-next 16.4.2.
    - Scripts: `dev` (`next dev`), `build`, `start`, `typecheck` (`tsc --noEmit`), `lint` (`eslint .`), and `check` (`tsc --noEmit && eslint . && node scripts/check-contrast.mjs`).
    - Add an `eslint.config.mjs` flat config built from eslint-config-next (core-web-vitals and typescript). It ignores `.next`, `node_modules`, and `next-env.d.ts`. Keep the `@/*` path alias in `tsconfig.json` with strict mode on.
    - Delete the legacy `web/app/insights/`, `web/lib/usePoll.ts`, `web/lib/occupancy.ts`, and `web/components/ZoneMap.tsx`.
    - Replace `app/page.tsx`, `app/map/page.tsx`, `app/plan/page.tsx`, and `app/demo/page.tsx` with title-only stubs, and add an `app/explore/page.tsx` stub, so the app type-checks until tasks 8–12 replace them.
    - Run `npm install` in `web/`, which updates `package-lock.json`, then `npm run typecheck` and `npm run lint`. No git.
    - _Requirements: 20.2, 20.3, 20.8_

  - [x] 7.2 Implement tokens, global styles, the root layout, and AppShell
    - Apple-design-skill: read the always-load set plus `tab-bars.md`, `sidebars.md`, `materials.md`, `liquid-glass.md`, `dark-mode.md`, `motion.md`, `focus-and-selection.md`, and `icons.md`.
    - `web/app/globals.css` holds:
      - every token from the design table, with dark values set only through `@media (prefers-color-scheme: dark)` and no in-app toggle
      - the system font stack, with body at 17/22 px
      - type-scale classes from Large Title to Caption, with nothing under 12 px, and a `tabular-nums` utility
      - a `:focus-visible` 3 px `--accent` outline at a 2 px offset
      - a 44 px minimum target rule for controls
      - a `.material` class for Floating_Controls (`backdrop-filter: blur(20px) saturate(180%)`), which turns opaque `--surface` under `prefers-reduced-transparency: reduce`
      - a `prefers-reduced-motion: reduce` rule that removes transitions
    - `web/app/layout.tsx` sets the metadata title "SpotStack" with the subtitle as the description, `lang="en"`, and a `viewport` export with `viewport-fit=cover`, and it wraps children in AppShell. It no longer imports Leaflet CSS.
    - `web/components/AppShell.tsx` and `AppShell.module.css`:
      - Below 768 px: a fixed bottom tab bar using `.material`, sitting above `env(safe-area-inset-bottom)`.
      - At 768 px and wider: a 220 px sidebar with the SpotStack wordmark.
      - Both show Home, Map, Plan, Explore, and Demo, each with an icon and a label. The current route gets `aria-current="page"`.
      - Add a Skip to Content link, and pad the content so the tab bar never covers it.
    - `web/components/Icons.tsx` is an inline SVG set (tabs, check, open circle, dotted circle, slashed circle, warning, chevrons, close) using `currentColor`, `aria-hidden`, and one stroke weight.
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.6, 17.8, 17.9, 17.10, 17.11, 17.12, 17.13, 17.14_

  - [x] 7.3 Implement the API client, live-stream hook, and formatters
    - `web/lib/api.ts`:
      - reads the base URL from `NEXT_PUBLIC_API_URL`, default `http://localhost:8000`
      - defines TypeScript types mirroring every response in the design's API contract, including `ValueState` and the error body
      - has a typed function per endpoint
      - throws `ApiRequestError` (status plus the API's `error`, `parameter`, and `message`) for API errors, and `ApiUnreachableError` when fetch throws a `TypeError`
    - `web/lib/useZoneStream.ts`, `useZoneStream(initialZones)`:
      - opens an `EventSource` on `/stream` and merges `snapshot` and `status` rows into `{zones, live}`
      - on error, sets `live=false`, closes the stream, and retries every 3 s
      - on reopen, refetches `/zones` and then sets `live=true`
    - `web/lib/format.ts`:
      - `percentFree` (rounded `(1 − occupied) × 100`)
      - `availabilityBand`: free ≥ 40, tight 15–39, full < 15, each with a text label
      - currency, time-limit text, minutes, and America/New_York time formatting
      - a converter from `datetime-local` to ISO with the offset
      - an `API_START_COMMAND` constant
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.9, 7.10, 14.5, 17.15, 17.16, 20.6_

  - [x] 7.4 Implement the shared ApiError, EmptyState, and Dial components
    - Apple-design-skill: read the always-load set plus `feedback.md`, `loading.md`, `writing.md`, and `gauges.md`.
    - `web/components/ApiError.tsx` and `ApiError.module.css` show the API's `message`, how to fix it, and a Try Again button. When the API is unreachable, they show the design's exact copy naming `uv run uvicorn app.main:create_app --factory --port 8000`. The component uses `role="alert"` and never apologizes.
    - `web/components/EmptyState.tsx` and `EmptyState.module.css` show a title, a description, and a next-action button or link.
    - `web/components/Dial.tsx` and `Dial.module.css`:
      - an SVG ring whose fill is proportional to percent free, colored by `--free`, `--tight`, or `--full`
      - a Caption capsule reading "62% free", plus the band label as text, so color is never the only signal
      - a 300 ms `stroke-dashoffset` transition that becomes instant under reduced motion
      - a pure `renderDialHtml(...)` helper with the same geometry, for Leaflet `divIcon`
    - _Requirements: 7.2, 7.3, 17.3, 17.4, 17.7, 17.8, 17.15, 17.16, 17.17_

  - [x] 7.5 Implement `web/scripts/check-contrast.mjs`
    - Parse the light and dark custom-property blocks from `web/app/globals.css`, and compute the WCAG contrast ratio for every pair:
      - `--text` and `--text-2` on `--bg`, `--surface`, `--surface-2`, and `--alternative`
      - `--on-accent` on `--accent`, and `--on-excluded` on `--excluded`
      - `--accent` and the band colors as text on the surfaces
    - Thresholds: 4.5:1 for normal text, 3:1 for text that's only large or bold, and 3:1 for the dial strokes and focus ring against their adjacent colors.
    - Print a table, and exit 1 on any failure.
    - If a pair fails, adjust only that token's hex value in `globals.css` (no other task in this wave edits it). Then run `npm run check`.
    - _Requirements: 17.5, 17.13, 20.8_

- [x] 8. Build the Home page
  - [x] 8.1 Implement Home at `/`
    - Apple-design-skill: read the always-load set plus `writing.md`, `branding.md`, `design-principles.md`, and `buttons.md`.
    - Files: `web/app/page.tsx` (server shell), `web/app/page.module.css`, and the client component `web/components/home/LiveCounts.tsx`.
    - The page shows "SpotStack" as a Large Title, the subtitle "South Bethlehem & Lehigh parking, live", and the thesis sentence from the design.
    - LiveCounts loads `/zones` and then follows `useZoneStream`. It shows Open Spaces Now (Σ capacity − active_sessions over visitor zones), Zones Opening Soon (the count with opening_soon > 0), and the Live or "Live updates paused" chip. It shows ApiError when a request fails.
    - Below that: links to Map, Plan, and Explore with title-style labels, such as "Open the Live Map" and "Plan a Visit"; a three-step How It Works; and a Data Sources section. Data Sources states that all data is synthetic, calibrated to the published BPA and Lehigh Parking Services rules, with placeholders flagged. It names the roadmap (Passport partner API, ParkMobile partner portal, BPA garage availability map) and points to `docs/integration.md`.
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 17.14, 17.15, 17.16_

- [x] 9. Build the Live Map
  - [x] 9.1 Implement the Leaflet ZoneMap component
    - Apple-design-skill: read the always-load set plus `maps.md`, `gauges.md`, `motion.md`, `dark-mode.md`, and `focus-and-selection.md`.
    - Files: `web/components/map/ZoneMap.tsx` (a client-only, plain Leaflet 1.9.4 component that imports `leaflet/dist/leaflet.css`) and `web/components/map/ZoneMap.module.css`.
    - Basemap: CARTO `light_all` or `dark_all` following `prefers-color-scheme` (including live changes), with attribution.
    - Markers:
      - Each zone is a `divIcon` dial at its facility coordinates, built with `renderDialHtml`. Zones that share a facility get distinct icon anchors so their dials don't stack.
      - Markers use `keyboard: true`, `role="button"`, and an `aria-label` such as "E 3rd St RapidPark West, 12% free". Enter and Space select.
      - Icons update in place on status changes, without remounting the map.
    - Props: `zones`, `selectedId`, `onSelect`, and `onMoveEnd(center)`.
    - When the selected zone changes, the map runs `flyTo`, or `setView(..., {animate: false})` under reduced motion.
    - On `tileerror`, it removes the tile layer and shows a plain `--surface-2` background, and the dials stay.
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.11, 7.12, 17.7, 17.8_

  - [x] 9.2 Implement the Map page, overlay panel, and lists
    - Apple-design-skill: read the always-load set plus `maps.md`, `materials.md`, `liquid-glass.md`, `lists-and-tables.md`, `feedback.md`, and `writing.md`.
    - Files: `web/app/map/page.tsx`, `web/app/map/page.module.css`, `web/components/map/MapView.tsx`, and `web/components/map/ZonePanel.tsx`. MapView is a client component that loads ZoneMap with `dynamic(() => import("./ZoneMap"), { ssr: false })`.
    - The page is titled "Live Map" and loads `/zones` on mount, then follows `useZoneStream`. Dials update within 1 s of a stream event. It shows the Live or "Live updates paused" chip and a legend with band colors and their text labels.
    - The overlay panel uses `.material` and floats on compact widths; on wide widths it sits to the side. It holds:
      - Selected zone details: zone, facility, operator, pay apps, rate, time limit, active of capacity, opening soon, note, and updated-at time.
      - An Opening Soon list from `/opening-soon?near=<center>`. It refetches on `moveend` (debounced 500 ms) and on stream updates, at most every 10 s. When empty, it shows "No spaces opening in the next 15 minutes" with a Plan a Visit link.
      - An All Zones button list as a non-map alternative. Selecting a zone flies to it.
    - ApiError shows on load failure.
    - _Requirements: 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.12, 17.7, 17.9, 17.10, 17.15, 17.16, 17.17_

- [x] 10. Build Plan a Visit
  - [x] 10.1 Implement Plan at `/plan`
    - Apple-design-skill: read the always-load set plus `entering-data.md`, `pickers.md`, `buttons.md`, `lists-and-tables.md`, `feedback.md`, and `writing.md`.
    - Files: `web/app/plan/page.tsx`, `web/app/plan/page.module.css`, and the client component `web/components/plan/PlanView.tsx`.
    - Destination radio cards from `/destinations` sit in a `fieldset` with a `legend`. The arrival time is a `datetime-local` input with the chips Now, In 1 Hour, Tonight 7 PM, and Saturday 12 PM, and it's sent as ISO with the America/New_York offset.
    - Once both are chosen, the page calls `/recommend` and shows ranked cards. Each card shows the rank, zone, facility, operator, rate, time limit, walk minutes, pay apps, and note.
    - Each card also shows any event warning (icon and text with the event name and start time), and labels results beyond the 25-minute walk. The score appears as text, such as "Availability 22% · Price 0.60 · Walk 1.00 → Score 0.53".
    - Show a loading state, ApiError on failure, and an EmptyState when there are no results.
    - _Requirements: 9.1, 9.2, 9.14, 17.4, 17.7, 17.14, 17.15, 17.16, 17.17_

- [x] 11. Build Explore
  - [x] 11.1 Implement selection history, the Selection_Bar, filter panes, and the state legend
    - Apple-design-skill: read the always-load set plus `toolbars.md`, `buttons.md`, `disclosure-controls.md`, `lists-and-tables.md`, `focus-and-selection.md`, and `voiceover.md`.
    - `web/lib/selectionHistory.ts` is a pure reducer over entries plus an index. `push` truncates the forward entries. It also provides `back`, `forward`, `canBack`, and `canForward`, and starts with an empty selection.
    - `web/components/explore/SelectionBar.tsx` has Back and Forward (disabled at their ends), Clear All, and a removable chip per field such as "Day: Saturday". Each chip's close control has an accessible name like "Clear Day Selection". The bar is sticky on compact widths.
    - `web/components/explore/FieldPane.tsx` renders values as buttons with a state icon, the value, and a count. Each button has `aria-pressed` and an accessible name that repeats the state, such as "Saturday, Selected, 2,210 sessions". On compact widths, each field sits behind a disclosure with `aria-expanded`.
    - `web/components/explore/StateLegend.tsx` shows the five states, each with color, icon, and label.
    - Styles go in `web/components/explore/Selection.module.css`.
    - _Requirements: 11.8, 11.13, 11.14, 11.15, 11.16, 11.17, 11.18, 11.19, 11.20, 17.4, 17.7_

  - [x] 11.2 Implement the KPI row, heatmap, and bar charts
    - Apple-design-skill: read the always-load set plus `charting-data.md`, `charts.md`, and `voiceover.md`.
    - `web/components/explore/KpiRow.tsx` shows five tiles: Sessions, Average Stay, Revenue, Overstay Rate, and Average Occupancy. A null value displays "—" with the accessible text "Not available".
    - `web/components/explore/Heatmap.tsx`:
      - a 7×24 grid of 44 px buttons with sticky day labels, scrolling horizontally on narrow screens
      - cells colored by the availability bands applied to 1 − occupancy, with the value shown as text
      - null cells in `--surface-2`, labeled "No sessions"
      - accessible names such as "Saturday 2 PM, 81% occupied"
      - `onSelect(day, hour)`
    - `web/components/explore/BarChart.tsx` draws horizontal bars from `div` buttons in a neutral `--text-2` color, so availability colors keep their single meaning. Each bar shows its value as text and has an accessible name, and the component exposes `onSelect(label)`.
    - Styles go in `web/components/explore/Charts.module.css`. Nothing animates.
    - _Requirements: 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.13, 16.4, 17.4, 17.7_

  - [x] 11.3 Wire the Explore page
    - Apple-design-skill: re-check the always-load set and `layout.md` for the compact and wide wireframes.
    - Files: `web/app/explore/page.tsx`, `web/app/explore/page.module.css`, and the client component `web/components/explore/ExploreView.tsx`.
    - On load, fetch `/explore/model` and run an initial `/explore/query`. Then each interaction posts the new selection and pushes it to history:
      - A value click calls `/explore/select`.
      - A heatmap cell queries with `Day=[day]` and `Arrival Hour=[hour]`.
      - A Sessions by Zone or turnover bar adds its Zone, and a stay-length bar adds its Stay Length bucket.
      - A chip clears its field, and Clear All sets `{}`.
    - Back and Forward re-query the stored selection.
    - Zero rows shows "No sessions match these selections" with Clear All. Previous results stay visible while a query loads, and ApiError shows on failure.
    - The page shows aggregates only.
    - _Requirements: 11.9, 11.10, 11.11, 11.12, 11.13, 11.14, 11.15, 11.16, 11.17, 11.18, 12.1, 12.9, 12.10, 12.11, 12.12, 12.14, 16.4, 17.15, 17.16, 17.17_

- [x] 12. Build the Demo Control Panel
  - [x] 12.1 Implement Demo at `/demo`
    - Apple-design-skill: read the always-load set plus `buttons.md`, `lists-and-tables.md`, `feedback.md`, `progress-indicators.md`, and `writing.md`.
    - Files: `web/app/demo/page.tsx`, `web/app/demo/page.module.css`, and the client component `web/components/demo/DemoPanel.tsx`.
    - Game Day, Family Weekend, and Reset buttons post `game_day`, `family_weekend`, and `reset` to `/demo/scenario`, with an in-flight state.
    - An active-scenario card shows the scenario name and the minutes remaining, from `/demo/status` plus a local 1 s timer.
    - A before/after table shows each affected zone's occupancy as percentages in text, with skipped reasons in text ("Already Full", "Not Enforced").
    - The presenter cue reads "Now open Map. Affected dials turn amber or red within 5 seconds." ApiError shows on failure.
    - _Requirements: 13.1, 13.7, 17.4, 17.14, 17.15, 17.16, 17.17_

- [x] 13. Write the project docs and environment file
  - [x] 13.1 Rewrite `README.md` at the workspace root in Devpost format
    - Replace the draft README. It has the sections Inspiration, What It Does, How We Built It, Challenges We Ran Into, Accomplishments That We're Proud Of, What We Learned, and What's Next.
    - Run instructions:
      - Prerequisites: uv, Python 3.13 installed by uv, and a Node.js version supported by Next.js 16 with npm.
      - The API command from `api/` and the web command from `web/`, with the URLs `http://localhost:8000` and `http://localhost:3000`.
      - The test and check commands.
    - Document the formulas for Estimated_Occupancy, Predicted_Occupancy, Walk_Minutes, and Recommendation_Score, with the default weights 0.5, 0.2, and 0.3.
    - State that all data is synthetic, and include the no-auth local note. Describe the deferred deploy path, naming `claude output/Hackathon` as a read-only reference. No git.
    - _Requirements: 19.1, 19.2, 19.3, 20.1, 20.2, 20.3, 20.8_

  - [x] 13.2 Write `docs/integration.md`
    - Cover the `SessionSource` seam and the rule that adapters drop plates and personal identifiers.
    - PassportSource: the Passport partner REST API, with OAuth client credentials issued to approved partners. The parking-environment export maps to Zone and Rate_Rule, and session events map to Session.
    - ParkMobileSource: requires the gated partner portal, and BPA's PayByPhone acceptance means ParkMobile alone undercounts.
    - The BPA garage availability map as a calibration and ground-truth source.
    - The statement that real integration needs data agreements with BPA and Lehigh Parking Services.
    - The local-to-scaffold table deltas from design.md, using `claude output/Hackathon` as a read-only reference.
    - _Requirements: 14.8, 18.1, 18.4, 18.5, 18.6, 18.7, 18.8_

  - [x] 13.3 Write `docs/demo-script.md`
    - Timed steps totaling ≤ 180 s: Home 20 s, Map 35 s, Plan 35 s, Demo with Map 45 s, and Explore 40 s.
    - Script the Game Day moment: trigger Game Day, watch the Map recolor the affected dials within 5 s, then select "Game Day (Live Demo)" in Explore's Event field to show its sessions and KPIs.
    - Include a pre-demo checklist: start both apps with the documented commands, then press Reset.
    - _Requirements: 19.4, 19.5_

  - [x] 13.4 Write the root `.env.example` and remove `web/.env.example`
    - List only names: `SEED_PATH`, `SIM_RNG_SEED`, `HISTORY_DAYS`, `CORS_ORIGINS`, and `NEXT_PUBLIC_API_URL`, each with a one-line comment and no value.
    - Delete the legacy `web/.env.example`, which uses the old `NEXT_PUBLIC_API_BASE_URL`.
    - Confirm the names match those read in `api/app/main.py` and `web/lib/api.ts`.
    - _Requirements: 20.6, 20.7_

  - [ ]* 13.5 Write the env-file smoke test in `api/tests/test_env_example.py`
    - Every entry in `../.env.example` is `NAME=` with no value, and the set of names equals the variables read by `app/main.py` and `web/lib/api.ts`.
    - _Requirements: 20.7_

- [ ] 14. Final verification and design review
  - [x] 14.1 Run every automated check and fix failures
    - Run `uv run pytest` in `api/`, including any optional tests that were written, then `npm run check` and `npm run build` in `web/`. Fix each failure in the file that owns it. No git.
    - _Requirements: 17.5, 20.5, 20.8_

  - [ ] 14.2 Smoke-test the running app
    - Start the API (`uv run uvicorn app.main:create_app --factory --port 8000` in `api/`) and the web app (`npm run dev` in `web/`) as background processes.
    - Curl every endpoint, including one error case each, and confirm that `/`, `/map`, `/plan`, `/explore`, and `/demo` return 200.
    - Hold `curl -N /stream` open while posting `game_day`, then confirm:
      - a `status` event arrives within 5 s
      - `/explore/model` lists "Game Day (Live Demo)" in the Event field within 10 s
      - `/demo/status` is active
    - Post `reset`, stop both processes, and delete any temp files.
    - _Requirements: 13.8, 15.1, 15.2, 15.10, 15.11, 19.5, 19.6, 20.1, 20.2, 20.5_

  - [ ] 14.3 Run an apple-design-skill review of the five screens and fix Critical and High findings
    - Use `SKILL.md` in code-audit mode against `web/`. Load the always-load set plus `tab-bars.md`, `sidebars.md`, `maps.md`, `gauges.md`, `charting-data.md`, `materials.md`, `motion.md`, `writing.md`, `feedback.md`, and `voiceover.md`.
    - Review Home, Map, Plan, Explore, and Demo through the five lenses. Report the findings in the task summary using the skill's report format, with no new markdown file.
    - Fix every Critical and High finding, then re-run `npm run check` and `npm run build`. List the manual checks still outstanding: VoiceOver, keyboard-only paths, reduced motion and transparency, 320 px and 1280 px widths, and offline tiles. No git.
    - _Requirements: 7.12, 11.8, 12.13, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9, 17.10, 17.11, 17.12, 17.13, 17.14, 17.15, 17.16, 17.17_

## Notes

- **Optional tasks:** sub-tasks marked `*` are optional. Required tests protect the demo: Property 5 (3.6), Property 14 (4.6), Property 19 (3.8), Property 22 (5.9), calibration and history budget (3.10), engine performance (4.11), and startup and smoke (5.11).
- **Property tests:** each one lives in its own file and uses hypothesis with `@settings(max_examples=100, deadline=None)`. Tag each with `# Feature: parking-monitor, Property N: <title>`. Simulator tests use small 2–3-day simulators from `conftest.py`, engine tests use `tests/engine_support.py`, and API tests use `create_app(sim=..., clock=fake, run_ticker=False)` in file-local fixtures.
- **No web test runner:** the web app relies on `npm run check` (types, lint, contrast) and the 14.3 design review. Full WCAG conformance still needs assistive-technology testing and an expert accessibility review.
- **Legacy code:** the draft modules break while the API is being rebuilt (from 2.2 until 5.2). That's expected. Tasks 3.1 and 5.2 replace `sim.py` and `main.py` in place.
- **Hard constraints:** none of these tasks run git commands or write to `claude output/`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "7.1"] },
    { "id": 1, "tasks": ["2.2", "5.1", "7.2", "7.3"] },
    { "id": 2, "tasks": ["2.3", "2.4", "2.5", "2.6", "7.4", "7.5"] },
    { "id": 3, "tasks": ["2.7", "3.1", "8.1", "9.1", "10.1", "11.1", "11.2", "12.1"] },
    { "id": 4, "tasks": ["3.2", "3.4", "3.5", "3.6", "4.1", "9.2", "11.3", "13.2", "13.3"] },
    { "id": 5, "tasks": ["3.3", "3.7", "4.2"] },
    { "id": 6, "tasks": ["3.8", "3.9", "3.10", "4.3", "4.4", "4.5", "4.6", "5.2"] },
    { "id": 7, "tasks": ["4.7", "4.8", "4.9", "4.10", "4.11", "5.3", "5.4", "5.5", "5.6", "5.7", "13.4"] },
    { "id": 8, "tasks": ["5.8", "5.9", "5.10", "5.11", "13.1", "13.5"] },
    { "id": 9, "tasks": ["14.1"] },
    { "id": 10, "tasks": ["14.2"] },
    { "id": 11, "tasks": ["14.3"] }
  ]
}
```
