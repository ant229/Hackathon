"""Parking Monitor API.

Stub mode (no SUPABASE_URL): every endpoint returns the shapes in fixtures/sample_responses.json,
so the frontend can build against it from hour 2.
Live mode: reads Supabase; prediction comes from the SQL function predict_availability().
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import db
from . import static_data as sd
from .models import (
    OpeningSoon,
    Prediction,
    Recommendation,
    ScenarioRequest,
    ScenarioResult,
    ZoneStatus,
)

app = FastAPI(title="Lehigh / South Bethlehem Parking API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@app.get("/health")
def health():
    return {"ok": True, "mode": "live" if db.live() else "stub"}


@app.get("/zones")
def zones():
    """Static zone metadata (name, coords, capacity, rate, pay app)."""
    return list(sd.zones().values())


@app.get("/status", response_model=list[ZoneStatus])
def status():
    if not db.live():
        return sd.samples()["zone_status"]
    return db.select("zone_status", {"order": "zone_id"})


def _predict(zone_id: int, at: datetime) -> Prediction:
    if not db.live():
        s = sd.samples()["predict"]
        return Prediction(**{**s, "zone_id": zone_id, "at": at})
    rows = db.rpc("predict_availability", {"p_zone_id": zone_id, "p_at": at.isoformat()})
    if not rows:
        raise HTTPException(404, f"zone {zone_id} not found")
    r = rows[0]
    return Prediction(zone_id=zone_id, at=at, expected_occupancy=r["expected_occupancy"],
                      prob_available=r["prob_available"], expected_open=r["expected_open"])


@app.get("/predict", response_model=Prediction)
def predict(zone: int = Query(..., description="zone_id"),
            time: datetime | None = Query(None, description="ISO time; default now")):
    if zone not in sd.zones():
        raise HTTPException(404, f"zone {zone} not found")
    return _predict(zone, time or _now())


@app.get("/opening-soon", response_model=OpeningSoon)
def opening_soon(lat: float, lng: float, max_walk: int = 15):
    if not db.live():
        return sd.samples()["opening_soon"]
    status_by_zone = {s["zone_id"]: s for s in db.select("zone_status")}
    out = []
    for z in sd.zones().values():
        if not z["visitor_allowed"]:
            continue
        walk = sd.walk_minutes(lat, lng, z["lat"], z["lng"])
        n = status_by_zone.get(z["id"], {}).get("opening_soon", 0)
        if walk <= max_walk and n > 0:
            out.append({"zone_id": z["id"], "name": z["name"], "opening_soon": n,
                        "walk_minutes": walk, "pay_app": z["pay_app"]})
    out.sort(key=lambda o: (o["walk_minutes"], -o["opening_soon"]))
    return {"near": {"lat": lat, "lng": lng}, "within_minutes": 15, "zones": out}


@app.get("/recommend", response_model=Recommendation)
def recommend(destination: int, arrival: datetime | None = None, limit: int = 3):
    dest = sd.destinations().get(destination)
    if not dest:
        raise HTTPException(404, f"destination {destination} not found")
    arrival = arrival or _now()
    if not db.live():
        s = sd.samples()["recommend"]
        return {**s, "destination": {"destination_id": dest["id"], "name": dest["name"]}, "arrival": arrival}

    options = []
    for z in sd.zones().values():
        if not z["visitor_allowed"]:
            continue
        walk = sd.walk_minutes(dest["lat"], dest["lng"], z["lat"], z["lng"])
        if walk > 20:
            continue
        p = _predict(z["id"], arrival)
        rate = z["hourly_rate"] or 0
        # Weighted score: availability matters most, then walk, then price. Tune freely.
        score = 0.55 * p.prob_available + 0.30 * max(0, 1 - walk / 20) + 0.15 * max(0, 1 - rate / 3)
        options.append({"zone_id": z["id"], "name": z["name"], "prob_available": p.prob_available,
                        "expected_open": p.expected_open, "hourly_rate": z["hourly_rate"],
                        "time_limit_min": z["time_limit_min"], "walk_minutes": walk,
                        "pay_app": z["pay_app"], "score": round(score, 3)})
    options.sort(key=lambda o: -o["score"])
    ranked = [{"rank": i + 1, **o} for i, o in enumerate(options[:limit])]
    return {"destination": {"destination_id": dest["id"], "name": dest["name"]},
            "arrival": arrival, "options": ranked}


# Demo scenarios: an event happening now, plus which zones it boosts.
SCENARIOS = {
    "game_day": {"name": "DEMO: Lehigh football game", "destination_id": 2, "hours": 3,
                 "attendance": 8000, "impacts": {12: 9.0, 1: 0.4, 2: 0.3, 8: 0.3}},
    "family_weekend": {"name": "DEMO: Family Weekend", "destination_id": 3, "hours": 6,
                       "attendance": 3000, "impacts": {6: 0.4, 8: 0.4, 9: 0.5, 10: 0.3, 11: 1.0, 2: 0.3}},
}


@app.post("/demo/scenario", response_model=ScenarioResult)
def demo_scenario(req: ScenarioRequest):
    if not db.live():
        return {**sd.samples()["demo_scenario"], "scenario": req.scenario}
    if req.scenario == "clear":
        db.delete("event", {"name": "like.DEMO:*"})
        return {"scenario": "clear", "event_id": None, "message": "Demo events cleared."}
    sc = SCENARIOS[req.scenario]
    start = _now()
    ev = db.insert("event", {"destination_id": sc["destination_id"], "name": sc["name"],
                             "start_time": start.isoformat(),
                             "end_time": (start + timedelta(hours=sc["hours"])).isoformat(),
                             "expected_attendance": sc["attendance"]})[0]
    db.insert("impacts", [{"event_id": ev["event_id"], "zone_id": z, "demand_boost": b}
                          for z, b in sc["impacts"].items()], returning=False)
    return {"scenario": req.scenario, "event_id": ev["event_id"],
            "message": f"{sc['name']} started; demand boosted for {sc['hours']} hours."}
