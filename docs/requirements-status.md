# Park LU Requirements Status

Source: `.kiro/specs/parking-monitor/requirements.md` (20 requirements, 224 acceptance criteria).
Data is entirely synthetic. The frontend has **not been exercised in a browser** against the live API.

Status key: **Met** (evidence exists), **Partial** (implemented with a stated gap), **Missing**, **Deferred** (deliberate scope cut), **Unverified (UI)** (code exists, behavior needs a browser to confirm).

Evidence key:

- `test_api`, `test_seed`, `test_prop_events`, `test_prop_geo`, `test_prop_time` are files in `api/tests/`. `uv run pytest -q` gives 62 passed.
- `calib` is an ad hoc script run on the 28-day, seed-7 simulator. It is not committed as a test (task 3.10 was not written).
- `code` means read and grep only, with no runtime check.
- Web: `tsc --noEmit`, `eslint .` and `npm run build` are clean. `web/scripts/check-contrast.mjs` passes 62 checks.

## Summary

224 criteria: **201 Met**, **3 Partial**, **20 Unverified (UI)**, 0 Missing, 0 Deferred.

**Deferred by project lead (not acceptance-criterion rows):** optional property tests (tasks marked `*`), the engine performance test (task 4.11), the apple-design review (task 14.3). Supabase hosting, deployment and auth are out of scope per the spec.

## Gaps to fix (ranked by demo impact)

1. **Browser smoke test not done (task 14.2).** Every Unverified (UI) row below, especially Map recolor within 5 s (7.5), the Demo to Map to Explore flow (19.5), and keyboard and tile-failure behavior, is code-only. Run the demo script once end to end before presenting.
2. **Game Day depends on the time of day.** `_inject` skips zones outside Enforcement_Hours (`skipped_reason: not_enforced`). At 21:29 on a Saturday, only 4 of 6 impacted zones changed (Packer Ave and E 3rd West were skipped). Demo Mon-Sat 08:00-21:00 for the full effect (13.3).
3. **Scenario targets are rounded down to whole spaces.** `_inject` uses `floor(0.95 * capacity)`. Small zones land under target: Packer Ave 0.80 to 0.92 (target 0.95), E 3rd West 0.911 to 0.933 (target 0.95). The tests allow a 0.03 tolerance. This is within one space, but not exact equality (13.3).
4. **Goodman Stadium recommendations are all 44-47 min walks.** No visitor zone is within 25 min, so `/recommend` returns the 3 closest as fallback (spec 9.6, correct). Demo Plan with Zoellner or 3rd Street shops instead (9.5/9.6).
5. **Explore Average Occupancy is approximate.** `associative.py:_aggregates` divides stay hours by `capacity * distinct_slots * weeks`. It attributes each session's whole stay to its arrival slot rather than spreading it across hours (12.6).
6. **Required test tasks not written:** 3.6, 3.8, 3.10 (calibration), 4.6, 5.9, 5.11 (smoke), and 5.4-5.8 / 5.10 / 13.5 (optional). Calibration (3.5-3.11) and scenario rules hold today only per the `calib` runs. Add `test_calibration.py` so they cannot regress silently.
7. **Session_Source covers only the Associative_Engine (18.1).** The Simulator reads its own sessions directly. That is inherent to the simulator design, but the spec wording says "every Session".
8. **3.7 passes with thin margin.** The worst baseline-vs-curve gap is 0.098 (limit 0.10), for `lps-farrington` at hour-of-week 143. A different seed or history length could breach it.

## Requirement 1: Data Model and Schema

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1.1 | Nine tables | Met | `data.py` dataclasses Operator, Facility, Zone, RateRule, Session, Destination, Event, Impact, ZoneStatus |
| 1.2 | Operator columns, Pay_App list | Met | `data.py:Operator.pay_app`; `test_seed::test_operators_and_pay_apps` |
| 1.3 | Facility columns, Type enum | Met | `data.py:Facility`; `_validate` type check (line 373) |
| 1.4 | Zone columns, positive capacity | Met | `data.py:Zone`; capacity check (line 383) |
| 1.5 | Rate_Rule columns, null limit | Met | `data.py:RateRule.time_limit_min` |
| 1.6 | Session columns, nullable Event_ID | Met | `data.py:Session` (plus internal `injected` flag) |
| 1.7 | Destination columns | Met | `data.py:Destination` |
| 1.8 | Event columns | Met | `data.py:Event` |
| 1.9 | Impacts composite key, boost >= 1 | Met | `data.py:Impact`; `_check_impact` (lines 354-359) |
| 1.10 | Zone_Status columns and ranges | Met | `data.py:ZoneStatus`; `_validate` (lines 435-437) |
| 1.11 | WGS84 decimal degrees | Met | `test_seed::test_facility_positions_are_decimal_degrees` |
| 1.12 | Relationships enforced | Met | `data.py:_validate` FK checks (lines 362-477) |
| 1.13 | Aware timestamps, New York local | Met | `test_prop_time` (naive raises, hour-of-week in New York time) |

## Requirement 2: Seed Data

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 2.1 | One JSON file in /fixtures | Met | `test_seed::test_seed_is_one_json_file_in_fixtures` |
| 2.2 | BPA and LPS operators, Pay_Apps | Met | `test_operators_and_pay_apps` |
| 2.3 | RapidPark $2.50 / 120 min | Met | `test_bpa_meter_rules` |
| 2.4 | FlexPark $1.50 / 180 min | Met | `test_bpa_meter_rules` |
| 2.5 | BPA street notes mention pay stations and apps | Met | `test_bpa_street_zones_note_pay_stations_and_apps` |
| 2.6 | Main, E 3rd, Morton zones | Met | `test_bpa_calibration_target_streets` |
| 2.7 | Polk 731, New Street Garage | Met | `test_polk_street_garage_capacity`, `test_new_street_garage_address` |
| 2.8 | Zoellner L1 visitor $1.00 to 23:00 | Met | `test_zoellner_level_1_visitor_rules` |
| 2.9 | Zoellner L2-4 permit only | Met | `test_zoellner_levels_2_to_4_are_permit_only` |
| 2.10 | Farrington capacity 52, $1.00, 06-24 | Met | `test_farrington_zone_and_rules` |
| 2.11 | Farrington note mentions Text2Park | Met | `test_farrington_note_mentions_text2park` |
| 2.12 | LPS Packer and Alumni L1 meters | Met | `test_lps_meter_zones` |
| 2.13 | Placeholder flags | Met | `test_placeholder_flags_match_design_catalog` |
| 2.14 | Source on verified rules | Met | `test_non_placeholder_rules_have_a_source` |
| 2.15 | Four destinations with lat/lng | Met | `test_four_destinations_with_positions` |
| 2.16 | 168-value demand curve per zone | Met | `test_every_zone_has_a_168_value_demand_curve` |

## Requirement 3: Synthetic Session Simulator

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 3.1 | At least 28 days of history | Met | `calib`: 136k sessions, history_days 28; API start about 1 s |
| 3.2 | Start inside enforcement hours | Met | `calib`: 0 of 136,117 outside a rule |
| 3.3 | Paid duration a positive multiple of 15 | Met | `calib`: 0 violations |
| 3.4 | Paid duration within Time_Limit_Min | Met | `calib`: 0 violations |
| 3.5 | Left Early 15-40% | Met | `calib`: 25.0% |
| 3.6 | Overstayed 5-20% | Met | `calib`: 11.9% |
| 3.7 | Mean occupancy within 0.10 of curve | Met | `calib`: worst gap 0.098, 0 slots over 0.10 (thin margin, see gap 8) |
| 3.8 | Active at or below capacity | Met | `calib`: peak concurrency check, no zone over capacity |
| 3.9 | Main/E 3rd >= 0.85, 10-18 Mon-Sat | Met | `calib`: 0.873-0.878 |
| 3.10 | Main/E 3rd turnover below BPA median | Met | `calib`: 5.74-5.77 vs median 6.26 |
| 3.11 | Morton <= 0.40 in enforcement | Met | `calib`: 0.331 |
| 3.12 | Boosted-start sessions tagged | Met | `calib`: 923 sampled, 0 untagged |
| 3.13 | Advance every 5 s or less | Met | `main.py:TICK_SECONDS = 2.0` |
| 3.14 | Deterministic with seed | Met | `calib`: two builds with seed 7 identical |

## Requirement 4: Recurring Event Templates

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 4.1 | Events from every template over the interval | Met | `test_prop_events::test_event_templates_expand_on_schedule` |
| 4.2 | Football alternating Saturdays 12-16 | Met | same test |
| 4.3 | Zoellner Fri/Sat 19:30-22:00 | Met | same test |
| 4.4 | Exactly one Family Weekend | Met | same test |
| 4.5 | Dates relative to start date | Met | same test (100 start dates, DST examples) |
| 4.6 | One Impacts row per template zone | Met | same test |
| 4.7 | Seed boosts >= 1.0 | Met | `test_seed::test_event_template_boosts_reference_zones_and_are_at_least_one` |

## Requirement 5: Live Occupancy Status

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 5.1 | Active_Sessions count | Met | `test_api::test_health_and_zones_shape` |
| 5.2 | Occupied = active / capacity | Met | same test (`approx(active / capacity)`) |
| 5.3 | Opening_Soon for limited zones | Met | `sim.py:opening_soon_counts`; `test_opening_soon_filters_zeros_and_sorts` |
| 5.4 | Opening_Soon 0 for unlimited zones | Met | `test_health_and_zones_shape` |
| 5.5 | Updated_At set | Met | `sim.py:_refresh_status` (code) |
| 5.6 | Update every 5 s or less | Met | `main.py` ticker, 2 s |

## Requirement 6: Demand Prediction

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 6.1 | Baseline from hourly-or-better samples | Met | `sim.py:_record_sample` (5-minute steps), `_finalize_history` |
| 6.2 | Exclude Boost_Window samples | Met | `sim.py:_record_sample` skips in-window (code; no dedicated test) |
| 6.3 | Event_Boost = max boost in window | Met | `sim.py:event_boost`; `test_api::test_scenario_lifecycle` |
| 6.4 | Predicted = baseline x boost, clamp 1.0 | Met | `test_predict_is_baseline_times_boost` |
| 6.5 | Availability = 1 - predicted | Met | same test |
| 6.6 | No ML library | Met | `pyproject.toml`: fastapi, uvicorn, numpy only |
| 6.7 | Predict returns the four values, null event | Met | `main.py:/predict` (baseline, boost, event_name, availability) |

## Requirement 7: Live Map

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 7.1 | One dial per zone at facility lat/lng | Unverified (UI) | `ZoneMap.tsx` |
| 7.2 | "N% free" text | Met | `dialMarkup.ts:98`, `format.ts:percentFree` |
| 7.3 | Fill and green/amber/red bands | Met | `format.ts:availabilityBand` (40/15 thresholds), `dialPin.css` |
| 7.4 | Load from /zones | Met | `MapView.tsx` (getZones), `lib/api.ts` |
| 7.5 | Update within 1 s of stream row | Unverified (UI) | `useZoneStream.ts` merges rows; timing needs a browser |
| 7.6 | Overlay panel fields | Unverified (UI) | `ZonePanel.tsx` |
| 7.7 | Opening-soon list for map center | Unverified (UI) | `MapView.tsx` (opening-soon fetch on center change) |
| 7.8 | Empty message with Plan link | Met | `ZonePanel.tsx:55` (string and link, code) |
| 7.9 | "Live updates paused", retry <= 5 s | Met | `useZoneStream.ts` (RETRY_MS 3000), `MapView.tsx:35` (code) |
| 7.10 | Reload /zones on reconnect | Met | `useZoneStream.ts` onopen to `getZones()` (code) |
| 7.11 | Dials and panel work with tiles failing | Unverified (UI) | `ZoneMap.tsx` |
| 7.12 | Keyboard reach, accessible name | Unverified (UI) | `dialMarkup.ts` aria-label includes zone and % free; keyboard flow not run |

## Requirement 8: Opening Soon

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 8.1 | Counts for next 0-15 min | Met | `test_opening_soon_filters_zeros_and_sorts` (`window_minutes` 15) |
| 8.2 | Zero-count zones omitted | Met | same test |
| 8.3 | Sorted by ascending distance | Met | same test |
| 8.4 | Result fields | Met | `main.py:/opening-soon` returns zone_id, zone_name, facility_name, opening_soon, distance_m, walk_minutes |
| 8.5 | Aggregates only | Met | same code; no session fields |
| 8.6 | Bad `near` gives 422 invalid_parameter | Met | `test_error_contract` (near) |

## Requirement 9: Plan a Visit

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 9.1 | List destinations on load | Met | `PlanView.tsx` (getDestinations on mount, code) |
| 9.2 | Request /recommend, ranked display | Met | `PlanView.tsx` (code) |
| 9.3 | Visitor-allowed zones only | Met | `test_recommend_rules` |
| 9.4 | Walk_Minutes formula | Met | `test_prop_geo::test_walk_minutes_matches_formula` |
| 9.5 | Exclude walk > 25 | Met | `calib`: far zones appear only when fewer than 3 are within 25 |
| 9.6 | Fill to 3 by ascending walk | Met | `calib`: Goodman returns 3 (walks 44-47) |
| 9.7 | Score formula | Met | `test_recommend_rules` (`0.5a + 0.2p + 0.3w`) |
| 9.8 | Weights 0.5/0.2/0.3 | Met | `/recommend` response `weights`; `test_recommend_rules` |
| 9.9 | Order by score, tie by walk | Met | `test_recommend_rules` |
| 9.10 | Weights and components in response | Met | live `/recommend` response |
| 9.11 | Rate, limit, Pay_App, walk, note | Met | live `/recommend` response |
| 9.12 | No rule gives rate 0, null limit, enforced false | Met | `test_recommend_rules` |
| 9.13 | Event warning | Met | live `/recommend` response (`event_warning`) |
| 9.14 | Display all result fields as text | Met | `PlanView.tsx` ResultCard (code) |
| 9.15 | Unknown destination gives 404 | Met | `test_not_found_and_unknown_scenario` |

## Requirement 10: Associative Data Model

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 10.1 | Load all sessions via source | Met | `main.py:start` (`engine.load(SimulatorSource)`); `/explore/model` row_count equals health sessions |
| 10.2 | Symbol table per field | Met | `associative.py` `symbols`; `test_engine_matches_brute_force` |
| 10.3 | Row index per session | Met | `associative.py` `cols`/`pos` |
| 10.4 | Required fields present | Met | live `/explore/model`: 12 fields (Zone ... Time Limit) |
| 10.5 | Day and Arrival Hour | Met | `test_engine_matches_brute_force` (Day) |
| 10.6 | Time_Of_Week_Class rules | Met | `associative.py:time_of_week` (code) |
| 10.7 | Stay buckets | Met | `associative.py:stay_bucket` (code) |
| 10.8 | Outcome with 5 min tolerance | Met | `associative.py:outcome`; brute-force test (Overstayed) |
| 10.9 | Event field or No Event | Met | `/explore/model` Event values (3) |
| 10.10 | Time Limit field | Met | `/explore/model` Time Limit (3 values) |
| 10.11 | Visitor Access field | Met | `/explore/model` (2 values) |
| 10.12 | New sessions added within 10 s | Met | `main.py:tick` calls `engine.sync()` every 2 s (code) |

## Requirement 11: Associative Selections and Value States

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 11.1 | OR within field, AND across | Met | `test_engine_matches_brute_force` |
| 11.2 | Recompute all states on change | Met | `test_explore_states_and_select` |
| 11.3 | Selected state | Met | `associative.py:_state`; same test |
| 11.4 | Selected_Excluded state | Met | `_state` (code; no dedicated test) |
| 11.5 | Possible state | Met | `_state` (code) |
| 11.6 | Alternative state | Met | `test_explore_states_and_select` (Monday alternative) |
| 11.7 | Excluded state | Met | same test (Weekday Class Hours excluded) |
| 11.8 | State shown by text or icon | Unverified (UI) | `StateLegend.tsx`, `FieldPane.tsx` |
| 11.9 | Click possible/alternative adds | Met | `AssociativeEngine.select` (code) |
| 11.10 | Click selected removes | Met | `test_explore_states_and_select` (toggle) |
| 11.11 | Click excluded replaces selection | Met | same test |
| 11.12 | Zero rows clears other fields | Met | `AssociativeEngine.select` (code; no dedicated test) |
| 11.13 | Selection_Bar lists selections | Unverified (UI) | `SelectionBar.tsx` |
| 11.14 | Per-field clear | Unverified (UI) | `ExploreView.tsx:onClearField` |
| 11.15 | Clear All | Unverified (UI) | `SelectionBar.tsx`, `ExploreView.tsx` |
| 11.16 | Back restores | Met | `lib/selectionHistory.ts:back` (pure logic, code) |
| 11.17 | Forward restores | Met | `selectionHistory.ts:forward` (code) |
| 11.18 | New selection discards forward | Met | `selectionHistory.ts:push` slices entries (code) |
| 11.19 | Back disabled at start | Met | `selectionHistory.ts:canBack`; `SelectionBar.tsx` aria-disabled |
| 11.20 | Forward disabled at end | Met | `selectionHistory.ts:canForward` |
| 11.21 | Response within 300 ms at 100k rows | Met | Manual: about 11 ms at about 137k rows. Automated test deferred (task 4.11) |

## Requirement 12: Explore KPIs and Charts

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 12.1 | Fields, bar, KPIs, charts on one view | Unverified (UI) | `ExploreView.tsx` |
| 12.2 | Sessions KPI | Met | `test_engine_matches_brute_force` |
| 12.3 | Average Stay KPI | Met | same test |
| 12.4 | Revenue KPI | Met | `associative.py:_aggregates` (sum of precomputed revenue; not brute-force tested) |
| 12.5 | Overstay Rate KPI | Met | `test_engine_matches_brute_force` |
| 12.6 | Average Occupancy KPI | Partial | `_aggregates` approximates: stay hours / (capacity x distinct arrival slots x weeks), attributed to arrival slot (gap 5) |
| 12.7 | 7x24 heatmap | Unverified (UI) | API returns 7x24 cells (`test_explore_states_and_select`); `Heatmap.tsx` render unverified |
| 12.8 | Three charts | Unverified (UI) | `ExploreView.tsx` BarCharts; API `charts` keys |
| 12.9 | All values replaced on change | Unverified (UI) | `ExploreView.tsx:run` |
| 12.10 | Heatmap click sets Day and Hour | Met | `ExploreView.tsx:onHeatmapSelect` (code) |
| 12.11 | Zone bar click adds zone | Unverified (UI) | `ExploreView.tsx` BarChart onSelect |
| 12.12 | Stay bar click adds bucket | Unverified (UI) | same |
| 12.13 | Accessible names on cells and bars | Met | `BarChart.tsx:128` aria-label label+value; `Heatmap.tsx` (code) |
| 12.14 | Empty message and Clear All | Met | `ExploreView.tsx:207` (code) |

## Requirement 13: Demo Control Panel and Scenarios

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 13.1 | Game Day / Family Weekend / Reset controls | Met | `DemoPanel.tsx` labels and POST (code) |
| 13.2 | Live event with template impacts | Met | `test_scenario_lifecycle`; `sim.py:_add_live_event` |
| 13.3 | Injected sessions reach target | Partial | `calib` and live: exact for most zones, but whole-space rounding leaves small zones up to 0.03 low, and non-enforced zones are skipped (gaps 2, 3) |
| 13.4 | Zones at >= 0.95 unchanged | Met | `test_scenario_lifecycle` (`already_full`) |
| 13.5 | Injected sessions follow rules, tagged | Met | `calib`: 315 injected, all multiples of 15, within limit, tagged |
| 13.6 | Response lists before/after per zone | Met | `test_scenario_lifecycle`; live response |
| 13.7 | Before/after %, name, minutes remaining | Met | `DemoPanel.tsx` (code); `/demo/status` `minutes_remaining` |
| 13.8 | Stream delivers changes within 5 s | Met | `main.py:demo_scenario` publishes changed rows immediately (code; Map render is 7.5) |
| 13.9 | Expires after 45 min | Met | `test_scenario_expires_after_45_minutes` |
| 13.10 | Reset ends injected sessions | Met | `test_scenario_lifecycle`; `calib` |
| 13.11 | New scenario replaces active | Met | `test_scenario_lifecycle` |
| 13.12 | Unknown scenario gives 400 and allowed list | Met | `test_not_found_and_unknown_scenario` |

## Requirement 14: Home Page

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 14.1 | Name and subtitle | Met | `app/page.tsx:17`, `AppShell.tsx:44` |
| 14.2 | One-sentence description | Met | `app/page.tsx:19` |
| 14.3 | Open spaces now (visitor zones) | Met | `LiveCounts.tsx` (sum of capacity minus active over visitor zones) |
| 14.4 | Zones opening soon | Met | `LiveCounts.tsx` (count of opening_soon > 0) |
| 14.5 | Live update without reload | Unverified (UI) | `LiveCounts.tsx` uses `useZoneStream` |
| 14.6 | Links to Map, Plan, Explore | Met | `app/page.tsx` links |
| 14.7 | Data Sources: synthetic, placeholders | Met | `app/page.tsx:87` |
| 14.8 | Integration roadmap | Met | `app/page.tsx:123-136` (Passport, ParkMobile, BPA map) |

## Requirement 15: Analytics API Endpoints

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 15.1 | GET /zones fields | Met | `test_health_and_zones_shape` |
| 15.2 | GET /stream is text/event-stream | Met | `test_stream_sends_snapshot` |
| 15.3 | Snapshot on connect | Met | same test |
| 15.4 | Changed rows within 5 s | Met | `main.py:tick` publishes each 2 s (code; SSE snapshot verified live) |
| 15.5 | Heartbeat <= 15 s | Met | `stream.py:DEFAULT_HEARTBEAT_S = 15.0` (code) |
| 15.6 | GET /destinations | Met | `test_recommend_rules` uses it; live (4 destinations) |
| 15.7 | GET /predict | Met | `test_predict_is_baseline_times_boost` |
| 15.8 | GET /opening-soon | Met | `test_opening_soon_filters_zeros_and_sorts` |
| 15.9 | GET /recommend, limit 1-20 default 5 | Met | `test_recommend_rules`, `test_error_contract` (limit 50) |
| 15.10 | POST /demo/scenario | Met | `test_scenario_lifecycle` |
| 15.11 | GET /explore/model | Met | live: 12 fields, row_count |
| 15.12 | POST /explore/query | Met | `test_explore_states_and_select` |
| 15.13 | POST /explore/select | Met | same test |
| 15.14 | Missing param gives 422 missing_parameter | Met | `test_error_contract` (zone) |
| 15.15 | Invalid param gives 422 invalid_parameter | Met | `test_error_contract` |
| 15.16 | Unknown id gives 404 not_found | Met | `test_not_found_and_unknown_scenario` |
| 15.17 | Unknown field/value gives 422 | Met | `test_explore_unknown_field_or_value` |
| 15.18 | CORS for localhost:3000 | Met | `main.py:122` (default origin; code) |

## Requirement 16: Privacy

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 16.1 | No plate column | Met | grep of `api/app` and `supabase/migrations`: no plate field |
| 16.2 | Aggregates only | Met | `test_responses_carry_no_identity_fields` |
| 16.3 | Engine returns no session IDs or rows | Met | same test (`/explore/query`) |
| 16.4 | Explore shows only aggregates | Met | `ExploreView.tsx` renders `/explore` aggregates only (code) |

## Requirement 17: UI Design and Accessibility

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 17.1 | System font stack | Met | `globals.css:54` |
| 17.2 | Body text 17 px | Met | `globals.css:102` (`max(17px, ...)`) |
| 17.3 | No text under 12 px | Met | grep: no `font-size` under 12 px in `app/` or `components/` |
| 17.4 | 44x44 hit areas | Unverified (UI) | `globals.css:275-276, 319-320` set 44 px on controls; map pins and chart bars need a browser check |
| 17.5 | Contrast 4.5:1 / 3:1 | Met | `check-contrast.mjs`: 62 passed, 0 failed (2 informational decorative) |
| 17.6 | Light/dark from OS only | Met | `globals.css:30` `prefers-color-scheme`; no toggle |
| 17.7 | Color paired with text/icon | Met | `Dial.tsx` band label, `ApiError.tsx` icon (code) |
| 17.8 | Reduced motion | Unverified (UI) | CSS in `globals.css:366`, `Dial.module.css`, `dialPin.css`, Leaflet options in `ZoneMap.tsx:268`; chart transitions not checked |
| 17.9 | Reduced transparency | Met | `globals.css:349` |
| 17.10 | Translucency only on floating controls | Unverified (UI) | `.material` in `globals.css` and `AppShell.module.css`; usage per surface not confirmed |
| 17.11 | Bottom tab bar at compact width | Met | `AppShell.tsx` (Home, Map, Plan, Explore, Demo), `AppShell.module.css` (code) |
| 17.12 | Sidebar at wide width | Met | `AppShell.module.css:141` `min-width: 768px` (code) |
| 17.13 | Focus indicator >= 3:1 | Met | `globals.css:324` `:focus-visible`; `check-contrast.mjs` "focus ring" rows PASS |
| 17.14 | Title-style capitalization | Met | labels in `AppShell.tsx`, `DemoPanel.tsx`, `ApiError.tsx` (code) |
| 17.15 | Error message with Try Again | Met | `ApiError.tsx`, `lib/api.ts` messages (code) |
| 17.16 | API unreachable names start command | Met | `lib/api.ts:287-290`, `format.ts:6` (code) |
| 17.17 | Empty states with next action | Met | `EmptyState.tsx` and its call sites (code) |

## Requirement 18: Integration Readiness

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 18.1 | Read sessions via Session_Source | Partial | Engine reads via `SimulatorSource` (`main.py:start`). The Simulator itself reads its own list (gap 7) |
| 18.2 | Simulator_Source is the only impl | Met | `sources.py` |
| 18.3 | Record has only the five fields | Met | `sources.py:SessionRecord` |
| 18.4 | Adapters must drop plates and identifiers | Met | `sources.py` docstring and `docs/integration.md` (documented rule; no adapters exist) |
| 18.5 | Passport adapter documented | Met | `docs/integration.md` |
| 18.6 | ParkMobile adapter documented | Met | `docs/integration.md` |
| 18.7 | BPA garage map as ground truth | Met | `docs/integration.md` |
| 18.8 | Data agreements statement | Met | `docs/integration.md` ("Data agreements") |

## Requirement 19: Hackathon Deliverables

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 19.1 | README sections | Met | `README.md` |
| 19.2 | Run instructions | Met | `README.md` "Run It" |
| 19.3 | Formulas, weights, synthetic statement | Met | `README.md` "Formulas" |
| 19.4 | Timed script, <= 180 s, five screens | Met | `docs/demo-script.md` (175 s) |
| 19.5 | Game Day moment scripted | Met | `docs/demo-script.md` steps 4-5. Not rehearsed in a browser (gap 1) |
| 19.6 | Scenario event in Explore within 10 s | Met | `test_scenario_lifecycle`; live check: `/explore/query` accepted `Game Day (Live Demo)` right after trigger |

## Requirement 20: Local Run Baseline

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 20.1 | One API command from /api | Met | `uv run uvicorn app.main:create_app --factory --port 8000`; started in this session |
| 20.2 | One web command from /web | Met | `npm run dev`; `npm run build` clean (dev server not opened in a browser) |
| 20.3 | No accounts, keys or hosted services | Met | No keys in code; public OSM tiles only |
| 20.4 | Data generated at startup | Met | `main.py:start` |
| 20.5 | Accepts requests within 30 s | Met | about 1 s to `/health` |
| 20.6 | NEXT_PUBLIC_API_URL, default :8000 | Met | `lib/api.ts:7` |
| 20.7 | Root .env.example, names only | Met | `.env.example` |
| 20.8 | One test command, one check command | Met | `cd api && uv run pytest`; `cd web && npm run check` |
