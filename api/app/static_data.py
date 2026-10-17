"""Static zone/facility/destination data, loaded from fixtures/zones.json (same source as the DB seed)."""
import json
import math
import os
from functools import lru_cache
from pathlib import Path

FIXTURES_DIR = Path(os.getenv("FIXTURES_DIR", Path(__file__).resolve().parents[2] / "fixtures"))


@lru_cache
def load() -> dict:
    return json.loads((FIXTURES_DIR / "zones.json").read_text())


@lru_cache
def samples() -> dict:
    return json.loads((FIXTURES_DIR / "sample_responses.json").read_text())


@lru_cache
def zones() -> dict[int, dict]:
    """zone_id -> zone dict enriched with facility, operator and first rate rule."""
    d = load()
    fac = {f["id"]: f for f in d["facilities"]}
    ops = {o["id"]: o for o in d["operators"]}
    out = {}
    for z in d["zones"]:
        f = fac[z["facility_id"]]
        rules = d["rate_templates"].get(str(z["id"]), [])
        first = rules[0] if rules else {}
        out[z["id"]] = {
            **z,
            "lat": f["lat"],
            "lng": f["lng"],
            "pay_app": ops[f["operator_id"]]["pay_app"],
            "hourly_rate": first.get("rate"),
            "time_limit_min": first.get("limit"),
        }
    return out


@lru_cache
def destinations() -> dict[int, dict]:
    return {d["id"]: d for d in load()["destinations"]}


def walk_minutes(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """Same formula as the SQL walk_minutes(): straight line x 1.3 detour at 80 m/min."""
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    meters = 2 * r * math.asin(math.sqrt(a))
    return math.ceil(meters * 1.3 / 80)
