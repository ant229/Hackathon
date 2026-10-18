# Park LU Integration Guide

The local build runs entirely on synthetic data: `fixtures/seed.json` supplies the
static tables, and the Python simulator (`api/app/sim.py`) generates Sessions in
memory. Everything in this guide beyond the seam itself is a plan, not shipped code.
Real integration requires data agreements with BPA and Lehigh Parking Services (see
[Data agreements](#data-agreements)).

This is the document that Home's Data Sources section links to (Req 14.8).

## The seam: `SessionSource`

The API and the associative engine read **every** Session through the `SessionSource`
protocol in `api/app/sources.py` (Req 18.1). Swapping the implementation changes no
route, engine, or UI code. In the local build the one and only implementation is
`SimulatorSource` (Req 18.2), which is backed by the simulator's session list and its
append-only change log.

The protocol has two methods. Each takes an integer cursor (start at `0`) and returns
`(items, new_cursor)`, where every item is an `(key, SessionRecord)` pair:

- `sessions_since(cursor)` — sessions added after the cursor, in arrival order, plus the
  new cursor.
- `changed_since(cursor)` — sessions whose fields changed after the cursor (for example,
  an `end_time` moved by a scenario reset), reported with their current values, each key
  once, plus the new cursor.

```python
@dataclass(frozen=True, slots=True)
class SessionRecord:
    zone_id: str
    start_time: datetime      # aware
    paid_until: datetime      # aware
    end_time: datetime        # aware
    event_id: str | None
```

`SessionRecord` holds **exactly** these five fields (Req 18.3) and nothing else. There is
no column for a license plate, name, phone number, email, or account/payment ID.

**Privacy rule (Req 18.4):** every adapter MUST drop license plates and personal
identifiers before it builds a `SessionRecord`, so none of them can reach the engine or
the Data_Store. The record's shape enforces this — whatever an operator's API returns,
only the five fields above survive the adapter. Keys are opaque integers used only for
in-engine row updates; they never leave the API.

## Planned adapters (not built)

### PassportSource — Lehigh Parking Services (Req 18.5)

Uses the Passport partner REST API (developer.passportinc.com) with **OAuth client
credentials issued to approved partners**. The adapter maps Passport data to Park LU's
tables:

- The **parking-environment export** maps to `Zone` and `Rate_Rule` (zones with capacity
  and visitor access; rate rules with day, time window, hourly rate, and time limit, with
  `placeholder = false` and a `source` set).
- **Session events** map to `Session`, keeping only zone, start, paid-until, end, and the
  optional event link. Plates and account data are discarded inside the adapter before a
  `SessionRecord` is built.

### ParkMobileSource — BPA on-street (Req 18.6)

Requires sign-up through the **gated ParkMobile partner developer portal**
(developer.parkmobile.io). Important caveat: **BPA also accepts PayByPhone**, so
**ParkMobile alone undercounts** BPA on-street sessions. Treat ParkMobile counts as a
lower bound until PayByPhone data is obtained through the same seam.

### BPA garage availability map — calibration and ground truth (Req 18.7)

The BPA public garage availability map (bethpark.org) is **not an adapter**. It is a
**calibration and ground-truth source** for the BPA garage zones: compare its published
availability against the simulator's (or a real source's) `Zone_Status.Occupied`, and tune
capacities and demand profiles to match. It is also where unverified (`placeholder`) rates
can be checked against reality. Park LU's Availability Dial deliberately echoes this
map's "more green = more available" cue so locals recognize it.

## Writing a real adapter

A real `SessionSource` (for example a `SupabaseSource`, or a per-operator adapter that
feeds Supabase) implements the same two methods:

1. **Ingest worker (service role).** Pull from Passport or ParkMobile, drop plates and
   personal identifiers, map the operator's zone to a Park LU `zone_id`, and insert into
   the Session table. Updates to `End_Time` or `Paid_Until` are updates to the same row.
2. **`sessions_since(cursor)`.** Select rows added after the cursor ordered by their id,
   and return `(id, SessionRecord(...))` pairs plus the highest id as the new cursor.
3. **`changed_since(cursor)`.** Needs a change marker. The simulator uses an append-only
   change log; a database source needs an equivalent (an append-only change table, or an
   `updated_at` column plus a sequence) added in a migration, then returns the current
   values for each changed key once.
4. **Recompute `Zone_Status`** (the `occupied` ratio, `active_sessions`, and
   `opening_soon` within 15 minutes) from sessions, exactly as the simulator does, so the
   live map numbers stay correct.

## Deferred deploy path: local → Supabase scaffold

The `claude output/Hackathon` scaffold is a **read-only reference** for the later deploy
phase (Supabase migrations, RLS, the Realtime publication, `fly.toml`, and CI). It is never
imported, run, or copied into the local build. Local tables map **1:1** to scaffold tables,
with the deltas below (from design.md's Deferred Deploy Path):

| Local | Scaffold | Migration note |
|---|---|---|
| `Session` | `parking_session` | rename (`session` is a SQL keyword); add a nullable `event_id` FK if absent |
| `Operator`, `Zone_Status`, … | lowercase snake case | names only |
| `Zone_Status.Occupied` (ratio) + `Active_Sessions` | `zone_status.occupied int` (count) | the count moves to `active_sessions`; `occupied` becomes a `numeric` ratio |
| `Zone.Note`, `Rate_Rule.placeholder`, `Rate_Rule.source` | absent | add columns |
| `Operator.Pay_App` list | text | `text[]` |
| SSE `/stream` | Realtime on `zone_status` | swap the web hook implementation |

The scaffold's `supabase/migrations/` splits the work into two files, kept separate so the
main schema still applies if `pg_cron` is unavailable:

- `20261017000000_init.sql` — the nine tables, the materialized analytics views and
  `refresh_analytics()`, row-level security (public read, service-role writes), and the
  Realtime publication on `zone_status`.
- `20261017000100_cron.sql` — enables `pg_cron` and schedules `refresh_analytics()` every
  10 minutes. Enable the `pg_cron` extension before applying it.

Schema conventions to keep in mind when mapping: `day_of_week` is `0 = Monday` (not
Postgres `dow`), local times are `America/New_York`, a demand boost is a multiplier of at
least `1.0`, and the Session table is named `parking_session`.

## Data agreements (Req 18.8)

Real integration requires **data agreements with the Bethlehem Parking Authority (BPA) and
Lehigh Parking Services**. They must cover access to partner APIs and credentials
(Passport, ParkMobile, and PayByPhone), permitted use of session data, a guarantee that no
plates or personal identifiers are stored, and permission to publish aggregate
availability.
