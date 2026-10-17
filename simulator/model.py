"""Demand model: how full each zone 'should' be at a given time, and what each parker does.

Calibrated to known patterns: 3rd St chronically full, Morton St quiet, campus busy on weekday
class hours, garages busy in the evening, Goodman lots empty except game days.
Everything is deterministic from (zone, time) so the backfill and the live loop agree.
"""
import hashlib
import math
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

# Share of capacity in use by hour (0-23), before the zone's own `demand` multiplier.
PROFILES = {
    "campus": {
        "weekday": [.05, .05, .05, .05, .05, .08, .15, .35, .70, .95, 1, 1, 1, 1, 1, .95, .80, .55, .40, .38, .35, .25, .12, .06],
        "weekend": [.05, .05, .05, .05, .05, .05, .08, .12, .20, .30, .40, .45, .45, .45, .42, .40, .35, .32, .30, .28, .22, .15, .08, .05],
    },
    "commercial": {
        "weekday": [.10, .08, .05, .05, .05, .05, .10, .20, .35, .55, .75, .90, .95, .90, .75, .70, .80, .95, 1, 1, .95, .75, .45, .20],
        "weekend": [.20, .12, .08, .05, .05, .05, .08, .15, .30, .50, .75, .95, 1, 1, .90, .85, .90, 1, 1, 1, 1, .85, .60, .35],
    },
    "daytime": {
        "weekday": [.05, .05, .05, .05, .05, .10, .25, .60, .90, 1, 1, 1, 1, 1, 1, .95, .80, .50, .30, .25, .20, .15, .10, .05],
        "weekend": [.05, .05, .05, .05, .05, .05, .08, .15, .25, .35, .40, .45, .45, .45, .45, .40, .38, .35, .35, .32, .28, .20, .12, .08],
    },
    "evening": {
        "weekday": [.12, .08, .05, .05, .05, .05, .08, .15, .25, .35, .45, .50, .55, .50, .45, .50, .65, .85, 1, 1, .95, .80, .50, .25],
        "weekend": [.25, .15, .08, .05, .05, .05, .08, .15, .30, .45, .55, .65, .70, .70, .65, .70, .80, .95, 1, 1, 1, .90, .70, .40],
    },
    "event_only": {
        "weekday": [.02] * 24,
        "weekend": [.02] * 24,
    },
}

# Typical paid duration in minutes when the zone has no time limit.
TYPICAL_STAY = {"campus": 150, "commercial": 100, "daytime": 240, "evening": 150, "event_only": 210}


def target_occupancy(zone: dict, t: datetime, boost: float = 0.0) -> float:
    """Fraction of capacity expected to be occupied at time t (0..0.98)."""
    local = t.astimezone(NY)
    prof = PROFILES[zone["profile"]]["weekend" if local.weekday() >= 5 else "weekday"]
    h, frac = local.hour, local.minute / 60
    base = prof[h] * (1 - frac) + prof[(h + 1) % 24] * frac   # smooth between hours
    occ = zone["demand"] * base * (1 + boost)
    if zone["profile"] == "event_only" and boost > 0:
        occ = max(occ, min(0.95, 0.12 * boost))
    return max(0.0, min(0.98, occ))


def _unit(*parts) -> float:
    """Deterministic pseudo-random number in [0, 1) from the given parts."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def _limit_options(limit: int) -> tuple[list[int], list[float]]:
    """Paid-duration choices under a time limit, weighted toward paying for longer."""
    options = [m for m in (30, 60, 90, 120, 150, 180, 240, 300) if m <= limit] or [limit]
    weights = [1 + (i if i < len(options) - 1 else i * 1.5) for i in range(len(options))]
    return options, weights


def paid_minutes(zone: dict, start: datetime, limit: int | None) -> int:
    u = _unit("paid", zone["id"], start.isoformat())
    if limit:
        options, weights = _limit_options(limit)
        x, acc = u * sum(weights), 0.0
        for m, w in zip(options, weights):
            acc += w
            if x < acc:
                return m
        return options[-1]
    mean = TYPICAL_STAY[zone["profile"]]
    m = mean * math.exp(0.5 * (u * 2 - 1))          # 0.6x .. 1.65x of typical
    return max(15, int(round(m / 15) * 15))


def actual_end(zone_id: int, start: datetime, paid_until: datetime) -> datetime:
    """When the car really leaves: 55%-115% of the paid time (~25% overstay)."""
    factor = 0.55 + 0.60 * _unit("dwell", zone_id, start.isoformat())
    return start + (paid_until - start) * factor


def mean_dwell_minutes(zone: dict, limit: int | None) -> float:
    if limit:
        options, weights = _limit_options(limit)
        return 0.85 * sum(o * w for o, w in zip(options, weights)) / sum(weights)
    return 0.85 * 1.042 * TYPICAL_STAY[zone["profile"]]   # 1.042 = mean of the lognormal spread


def arrivals(zone: dict, t: datetime, minutes: float, boost: float, limit: int | None, rng: random.Random) -> int:
    """Poisson arrivals over `minutes` so occupancy tracks the target (Little's law)."""
    lam = zone["capacity"] * target_occupancy(zone, t, boost) / mean_dwell_minutes(zone, limit) * minutes
    # Poisson sample (Knuth for small lambda, normal approx for large).
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def new_session(zone: dict, start: datetime, limit: int | None) -> dict:
    start = start.replace(microsecond=0)
    paid_until = start + timedelta(minutes=paid_minutes(zone, start, limit))
    return {"zone_id": zone["id"], "start_time": start, "paid_until": paid_until,
            "end_time": actual_end(zone["id"], start, paid_until)}
