"""End-to-end checks of the API contract, scenarios, engine, privacy, and errors.

One module-scoped app on a 7-day simulator with a fake clock (no ticker), so
tests drive time explicitly.
"""
from datetime import timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.associative import AssociativeEngine
from app.main import create_app
from app.sim import build_simulator
from app.sources import SimulatorSource
from tests.conftest import START, FakeClock


@pytest.fixture(scope="module")
def clock():
    return FakeClock(START)


@pytest.fixture(scope="module")
def client(clock):
    sim = build_simulator(start=START, history_days=7, rng_seed=7)
    sim.generate_history()
    with TestClient(create_app(sim=sim, clock=clock, run_ticker=False)) as c:
        yield c


def test_health_and_zones_shape(client):
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["sessions"] > 0
    zones = client.get("/zones").json()["zones"]
    assert len(zones) == health["zones"]
    z = zones[0]
    for key in ("zone_id", "zone_name", "facility_name", "facility_type", "operator", "pay_app", "note", "lat",
                "lng", "capacity", "visitor_allowed", "hourly_rate", "time_limit_min", "enforced", "status"):
        assert key in z
    for z in zones:
        st = z["status"]
        assert 0 <= st["occupied"] <= 1 and st["active_sessions"] <= z["capacity"]
        assert st["occupied"] == pytest.approx(st["active_sessions"] / z["capacity"], abs=1e-4)
        if z["time_limit_min"] is None:
            assert st["opening_soon"] == 0


def test_predict_is_baseline_times_boost(client):
    zid = client.get("/zones").json()["zones"][0]["zone_id"]
    p = client.get("/predict", params={"zone": zid, "time": "2026-10-16T13:00:00"}).json()
    assert p["predicted_occupancy"] == pytest.approx(min(1, p["baseline_occupancy"] * p["event_boost"]), abs=1e-3)
    assert p["predicted_availability"] == pytest.approx(1 - p["predicted_occupancy"], abs=1e-3)


def test_opening_soon_filters_zeros_and_sorts(client):
    body = client.get("/opening-soon", params={"near": "40.607,-75.378"}).json()
    assert body["window_minutes"] == 15
    assert all(r["opening_soon"] > 0 for r in body["results"])
    assert [r["distance_m"] for r in body["results"]] == sorted(r["distance_m"] for r in body["results"])


def test_recommend_rules(client):
    dests = client.get("/destinations").json()["destinations"]
    zones = {z["zone_id"]: z for z in client.get("/zones").json()["zones"]}
    for d in dests:
        body = client.get("/recommend", params={"destination": d["destination_id"],
                                                "arrival": "2026-10-17T13:00:00", "limit": 20}).json()
        res = body["results"]
        assert len(res) >= 3
        assert all(zones[r["zone_id"]]["visitor_allowed"] for r in res)
        assert [r["rank"] for r in res] == list(range(1, len(res) + 1))
        keys = [(-r["score"], r["walk_minutes"]) for r in res]
        assert keys == sorted(keys)
        for r in res:
            expect = 0.5 * r["predicted_availability"] + 0.2 * r["price_score"] + 0.3 * r["walk_score"]
            assert r["score"] == pytest.approx(expect, abs=1e-3)
            if not r["enforced"]:
                assert r["hourly_rate"] == 0 and r["time_limit_min"] is None


@pytest.mark.parametrize("path,params,code,param", [
    ("/predict", {"time": "2026-10-17T15:00:00"}, "missing_parameter", "zone"),
    ("/predict", {"zone": "x", "time": "nope"}, "invalid_parameter", "time"),
    ("/opening-soon", {"near": "40.6"}, "invalid_parameter", "near"),
    ("/recommend", {"destination": "zoellner", "arrival": "2026-10-17T15:00:00", "limit": 50},
     "invalid_parameter", "limit"),
])
def test_error_contract(client, path, params, code, param):
    res = client.get(path, params=params)
    assert res.status_code == 422
    assert res.json()["error"] == code and res.json()["parameter"] == param and res.json()["message"]


def test_not_found_and_unknown_scenario(client):
    res = client.get("/recommend", params={"destination": "goodmann", "arrival": "2026-10-17T15:00:00"})
    assert res.status_code == 404 and "goodmann" in res.json()["message"]
    res = client.post("/demo/scenario", json={"scenario": "tailgate"})
    assert res.status_code == 400 and res.json()["allowed"] == ["game_day", "family_weekend", "reset"]


def test_scenario_lifecycle(client, clock):
    clock.advance(minutes=1)
    body = client.post("/demo/scenario", json={"scenario": "game_day"}).json()
    assert body["event"]["name"] == "Game Day (Live Demo)"
    for a in body["affected"]:
        if a["skipped_reason"] is None:
            assert a["occupied_after"] >= min(0.95, a["occupied_before"] + 0.25) - 0.03
            assert a["occupied_after"] <= 0.95 + 1e-9
        elif a["skipped_reason"] == "already_full":
            assert a["occupied_after"] == a["occupied_before"]
    status = client.get("/demo/status").json()["active"]
    assert status["scenario"] == "game_day" and 0 < status["minutes_remaining"] <= 45
    # The live event is explorable right away (Req 19.6).
    events = next(f for f in client.get("/explore/model").json()["fields"] if f["name"] == "Event")["values"]
    assert "Game Day (Live Demo)" in events
    # Switching ends the old scenario; reset clears everything.
    clock.advance(minutes=1)
    assert client.post("/demo/scenario", json={"scenario": "family_weekend"}).json()["scenario"] == "family_weekend"
    clock.advance(minutes=1)
    assert client.post("/demo/scenario", json={"scenario": "reset"}).json()["event"] is None
    assert client.get("/demo/status").json() == {"active": None}


def test_scenario_expires_after_45_minutes(client, clock):
    clock.advance(minutes=1)
    client.post("/demo/scenario", json={"scenario": "game_day"})
    clock.advance(minutes=46)
    client.app.state.tick()
    assert client.get("/demo/status").json() == {"active": None}


def test_explore_states_and_select(client):
    base = client.post("/explore/query", json={"selection": {}}).json()
    total = base["kpis"]["sessions"]
    assert total == client.get("/explore/model").json()["row_count"]
    sat = client.post("/explore/select", json={"selection": {}, "field": "Day", "value": "Saturday"}).json()
    assert sat["selection"] == {"Day": ["Saturday"]}
    day = {v["value"]: v["state"] for v in next(f for f in sat["fields"] if f["name"] == "Day")["values"]}
    assert day["Saturday"] == "selected" and day["Monday"] == "alternative"
    tow = {v["value"]: v["state"] for v in next(f for f in sat["fields"] if f["name"] == "Time of Week")["values"]}
    assert tow["Weekday Class Hours"] == "excluded"
    # Clicking an excluded value replaces the incompatible selection.
    res = client.post("/explore/select", json={"selection": {"Day": ["Saturday"]}, "field": "Time of Week",
                                               "value": "Weekday Class Hours"}).json()
    assert res["selection"] == {"Time of Week": ["Weekday Class Hours"]}
    # Toggling a selected value removes it.
    off = client.post("/explore/select", json={"selection": {"Day": ["Saturday"]}, "field": "Day",
                                               "value": "Saturday"}).json()
    assert off["selection"] == {} and off["kpis"]["sessions"] == total
    assert len(base["heatmap"]["cells"]) == 7 and len(base["heatmap"]["cells"][0]) == 24


def test_explore_unknown_field_or_value(client):
    res = client.post("/explore/query", json={"selection": {"Colour": ["Red"]}})
    assert res.status_code == 422 and res.json()["error"] == "invalid_parameter"
    res = client.post("/explore/query", json={"selection": {"Day": ["Funday"]}})
    assert res.status_code == 422 and res.json()["parameter"] == "Day"


def test_engine_matches_brute_force():
    sim = build_simulator(start=START, history_days=2, rng_seed=3)
    sim.generate_history()
    engine = AssociativeEngine(sim.store, 2)
    engine.load(SimulatorSource(sim))
    res = engine.query({"Day": ["Tuesday"], "Outcome": ["Overstayed"]})
    expect = [s for s in sim.sessions
              if s.start_time.astimezone(START.tzinfo).weekday() == 1 and s.end_time > s.paid_until + timedelta(minutes=5)]
    assert res["kpis"]["sessions"] == len(expect)
    if expect:
        stay = np.mean([(s.end_time - s.start_time).total_seconds() / 60 for s in expect])
        assert res["kpis"]["avg_stay_min"] == pytest.approx(stay, abs=0.1)
        assert res["kpis"]["overstay_rate"] == 1.0


def test_responses_carry_no_identity_fields(client):
    for method, path, kw in [("get", "/zones", {}), ("get", "/health", {}),
                             ("post", "/explore/query", {"json": {"selection": {}}})]:
        text = getattr(client, method)(path, **kw).text.lower()
        assert "plate" not in text and "session_id" not in text


def test_stream_sends_snapshot(client):
    with client.stream("GET", "/stream", params={"max_events": 1}) as res:
        assert res.headers["content-type"].startswith("text/event-stream")
        body = "".join(res.iter_text())
    assert body.startswith("event: snapshot") and '"zones"' in body
