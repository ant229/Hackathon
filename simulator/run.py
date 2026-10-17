"""Synthetic payment-session simulator.

  python -m simulator.run --dry-run        # no database; prints a sanity report
  python -m simulator.run --backfill 14    # load 14 days of history, then run live
  python -m simulator.run                  # live loop (backfills 14 days if the DB is empty)

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for anything but --dry-run.
Run from the repo root.
"""
import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from simulator.model import NY, arrivals, new_session, target_occupancy

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "fixtures" / "zones.json").read_text())
ZONES = {z["id"]: z for z in DATA["zones"]}
TICK_SECONDS = int(os.getenv("SIM_TICK_SECONDS", "60"))


def time_limit(zone_id: int) -> int | None:
    rules = DATA["rate_templates"].get(str(zone_id), [])
    return rules[0].get("limit") if rules else None


# ---------------------------------------------------------------- historical events

def historical_events(start: datetime, end: datetime) -> list[dict]:
    """Recurring events so analytics show event impact: Saturday games, Fri/Sat shows."""
    evs, day = [], start.astimezone(NY).replace(hour=0, minute=0, second=0, microsecond=0)
    week = 0
    while day < end:
        if day.weekday() == 5:       # Saturday
            week += 1
            if week % 2 == 0:        # home game every other Saturday
                evs.append({"name": "Lehigh football (sim)", "destination_id": 2,
                            "start": day.replace(hour=12), "end": day.replace(hour=16),
                            "attendance": 8000, "impacts": {12: 9.0, 1: 0.4, 2: 0.3, 8: 0.3}})
        if day.weekday() in (4, 5):  # Fri/Sat Zoellner show
            evs.append({"name": "Zoellner show (sim)", "destination_id": 1,
                        "start": day.replace(hour=19, minute=30), "end": day.replace(hour=22),
                        "attendance": 900, "impacts": {6: 0.5, 7: 0.3, 10: 0.4, 1: 0.2}})
        day += timedelta(days=1)
    return [e for e in evs if start <= e["end"] and e["start"] <= end]


def boost_at(events: list[dict], zone_id: int, t: datetime) -> float:
    b = 0.0
    for e in events:
        if e["start"] - timedelta(hours=1) <= t <= e["end"]:
            b += e["impacts"].get(zone_id, 0.0)
    return b


# ---------------------------------------------------------------- generation

def generate(start: datetime, end: datetime, events: list[dict], now: datetime, rng: random.Random,
             step_min: int = 5) -> list[dict]:
    import heapq
    rows, t = [], start
    parked: dict[int, list] = {zid: [] for zid in ZONES}   # min-heap of end times per zone
    while t < end:
        for z in ZONES.values():
            heap = parked[z["id"]]
            while heap and heap[0] <= t:
                heapq.heappop(heap)
            lim = time_limit(z["id"])
            n = arrivals(z, t, step_min, boost_at(events, z["id"], t), lim, rng)
            n = min(n, z["capacity"] - len(heap))   # full zone: drivers circle and go elsewhere
            for _ in range(max(0, n)):
                s = new_session(z, t + timedelta(seconds=rng.randint(0, step_min * 60 - 1)), lim)
                heapq.heappush(heap, s["end_time"])
                if s["end_time"] > now:
                    s["end_time"] = None            # still parked
                rows.append(s)
        t += timedelta(minutes=step_min)
    return rows


def warmup_start(now: datetime, days: int) -> datetime:
    return now - timedelta(days=days)


# ---------------------------------------------------------------- supabase

class DB:
    def __init__(self):
        url, key = os.getenv("SUPABASE_URL", "").rstrip("/"), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not (url and key):
            raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
        self.c = httpx.Client(base_url=f"{url}/rest/v1", timeout=60, headers={
            "apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    def get(self, table, **params):
        r = self.c.get(f"/{table}", params={"select": "*", **params})
        r.raise_for_status()
        return r.json()

    def insert(self, table, rows, returning=False):
        out = []
        for i in range(0, len(rows), 1000):
            r = self.c.post(f"/{table}", content=json.dumps(rows[i:i + 1000], default=str),
                            headers={"Prefer": "return=representation" if returning else "return=minimal"})
            r.raise_for_status()
            if returning:
                out += r.json()
        return out

    def patch(self, table, values, **params):
        self.c.patch(f"/{table}", params=params, content=json.dumps(values, default=str)).raise_for_status()

    def rpc(self, fn, **args):
        self.c.post(f"/rpc/{fn}", json=args).raise_for_status()


def save_events(db: DB, events: list[dict]):
    for e in events:
        ev = db.insert("event", [{"destination_id": e["destination_id"], "name": e["name"],
                                  "start_time": e["start"].isoformat(), "end_time": e["end"].isoformat(),
                                  "expected_attendance": e["attendance"]}], returning=True)[0]
        db.insert("impacts", [{"event_id": ev["event_id"], "zone_id": z, "demand_boost": b}
                              for z, b in e["impacts"].items()])


def load_db_events(db: DB) -> list[dict]:
    """Events (incl. demo scenarios created by the API) overlapping the next few hours."""
    now = datetime.now(timezone.utc)
    evs = db.get("event", end_time=f"gte.{now.isoformat()}",
                 start_time=f"lte.{(now + timedelta(hours=2)).isoformat()}")
    out = []
    for e in evs:
        imps = db.get("impacts", event_id=f"eq.{e['event_id']}")
        out.append({"start": datetime.fromisoformat(e["start_time"]), "end": datetime.fromisoformat(e["end_time"]),
                    "impacts": {i["zone_id"]: i["demand_boost"] for i in imps}})
    return out


def backfill(db: DB, days: int, rng: random.Random):
    now = datetime.now(timezone.utc)
    start = warmup_start(now, days)
    events = historical_events(start, now + timedelta(days=7))
    print(f"backfill: {days} days, {len(events)} events", flush=True)
    save_events(db, events)
    rows = generate(start, now, events, now, rng)
    print(f"backfill: inserting {len(rows)} sessions", flush=True)
    db.insert("parking_session", [{**r, "start_time": r["start_time"].isoformat(),
                                   "paid_until": r["paid_until"].isoformat(),
                                   "end_time": r["end_time"].isoformat() if r["end_time"] else None}
                                  for r in rows])
    db.rpc("refresh_zone_status")
    db.rpc("refresh_analytics")
    print("backfill: done", flush=True)


def live_loop(db: DB, rng: random.Random):
    from simulator.model import actual_end
    tick = 0
    while True:
        now = datetime.now(timezone.utc)
        events = load_db_events(db)
        # 1. departures: active sessions whose planned end has passed
        active = db.get("parking_session", end_time="is.null", limit="20000")
        leaving = [s["session_id"] for s in active
                   if actual_end(s["zone_id"], datetime.fromisoformat(s["start_time"]),
                                 datetime.fromisoformat(s["paid_until"])) <= now]
        for i in range(0, len(leaving), 300):
            db.patch("parking_session", {"end_time": now.isoformat()},
                     session_id=f"in.({','.join(map(str, leaving[i:i + 300]))})")
        # 2. arrivals over the last tick (capped at free spaces)
        left = set(leaving)
        still = defaultdict(int)
        for s in active:
            if s["session_id"] not in left:
                still[s["zone_id"]] += 1
        new = []
        for z in ZONES.values():
            lim = time_limit(z["id"])
            n = arrivals(z, now, TICK_SECONDS / 60, boost_at(events, z["id"], now), lim, rng)
            n = max(0, min(n, z["capacity"] - still[z["id"]]))
            for _ in range(n):
                s = new_session(z, now - timedelta(seconds=rng.randint(0, TICK_SECONDS - 1)), lim)
                new.append({"zone_id": s["zone_id"], "start_time": s["start_time"].isoformat(),
                            "paid_until": s["paid_until"].isoformat(), "end_time": None})
        if new:
            db.insert("parking_session", new)
        db.rpc("refresh_zone_status")
        if tick % 10 == 0:
            db.rpc("refresh_analytics")
        print(f"{now:%H:%M:%S} +{len(new)} arrived, -{len(leaving)} left, {len(events)} active events", flush=True)
        tick += 1
        time.sleep(TICK_SECONDS)


# ---------------------------------------------------------------- dry run

def dry_run(days: int, rng: random.Random):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = warmup_start(now, days)
    events = historical_events(start, now)
    rows = generate(start, now, events, now, rng)
    print(f"{len(rows)} sessions over {days} days, {len(events)} events")
    # occupancy check at weekday 12:00 and Saturday 19:00 local, last week
    samples = defaultdict(list)
    t = start + timedelta(days=1)
    while t < now:
        loc = t.astimezone(NY)
        key = None
        if loc.weekday() < 5 and loc.hour == 12:
            key = "weekday noon"
        elif loc.weekday() == 5 and loc.hour == 19:
            key = "Saturday 7pm"
        if key:
            for z in ZONES.values():
                parked = sum(1 for r in rows if r["zone_id"] == z["id"] and r["start_time"] <= t
                             and (r["end_time"] is None or r["end_time"] > t))
                samples[(key, z["id"])].append(parked / z["capacity"])
        t += timedelta(hours=1)
    print(f"{'zone':32} {'weekday noon':>13} {'Sat 7pm':>9}  target@now")
    for z in ZONES.values():
        a = samples.get(("weekday noon", z["id"]), [0])
        b = samples.get(("Saturday 7pm", z["id"]), [0])
        print(f"{z['name']:32} {sum(a)/len(a):13.0%} {sum(b)/len(b):9.0%}  {target_occupancy(z, now):.0%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backfill", type=int, default=None, help="days of history to load first")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    if args.dry_run:
        return dry_run(args.backfill or 7, rng)

    try:
        db = DB()
    except RuntimeError as e:
        print(f"simulator idle: {e}", flush=True)
        while True:            # keep the Fly worker alive instead of crash-looping
            time.sleep(3600)

    if args.backfill:
        backfill(db, args.backfill, rng)
    elif not db.get("parking_session", limit="1"):
        backfill(db, 14, rng)
    live_loop(db, rng)


if __name__ == "__main__":
    sys.exit(main())
