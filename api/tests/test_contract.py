"""Stub-mode tests: every endpoint returns the contract shapes from fixtures/sample_responses.json."""
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_stub_mode():
    assert client.get("/health").json() == {"ok": True, "mode": "stub"}


def test_zones_has_static_metadata():
    zones = client.get("/zones").json()
    assert len(zones) == 12
    assert {"id", "name", "lat", "lng", "capacity", "pay_app"} <= zones[0].keys()


def test_status():
    rows = client.get("/status").json()
    assert len(rows) == 12 and {"zone_id", "occupied", "opening_soon"} <= rows[0].keys()


def test_predict():
    r = client.get("/predict", params={"zone": 3})
    assert r.status_code == 200
    assert 0 <= r.json()["prob_available"] <= 1


def test_predict_unknown_zone():
    assert client.get("/predict", params={"zone": 999}).status_code == 404


def test_opening_soon():
    body = client.get("/opening-soon", params={"lat": 40.6077, "lng": -75.3735}).json()
    assert body["zones"] and "walk_minutes" in body["zones"][0]


def test_recommend():
    body = client.get("/recommend", params={"destination": 1}).json()
    assert body["destination"]["name"] == "Zoellner Arts Center"
    assert [o["rank"] for o in body["options"]] == [1, 2, 3]


def test_demo_scenario():
    r = client.post("/demo/scenario", json={"scenario": "game_day"})
    assert r.status_code == 200 and r.json()["scenario"] == "game_day"
