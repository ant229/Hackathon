"""Calibration and history-budget checks for the default simulator (Req 3).

These example tests protect the demo numbers. They all read the session-scoped
``default_sim`` (full seed, 28 days of history, seed 7), so they never mutate
it: no ``advance_to`` and no scenarios. One extra test builds a fresh simulator
to time ``generate_history()``.

What each check covers:

- **History span** (Req 3.1): the simulated window is at least 28 days long and
  ends exactly at ``start``.
- **Outcome shares** (Req 3.5, 3.6): across every generated Session, the Left
  Early share lands in [0.15, 0.40] and the Overstayed share in [0.05, 0.20].
  Outcomes use the 5-minute tolerance from the Explore Outcome field: a Session
  is Left Early when ``end < paid_until - 5 min``, Overstayed when ``end >
  paid_until + 5 min``, else On Time.
- **Per-slot calibration** (Req 3.7): for every zone and every Hour_Of_Week that
  has non-boosted history samples, the mean Estimated_Occupancy
  (``baseline``) is within 0.10 of the zone's demand-curve target.
- **Core occupancy** (Req 3.9): Main St and E 3rd St average at least 0.85 from
  10:00 to 18:00, Monday through Saturday.
- **Turnover ordering** (Req 3.10): Main St and E 3rd St turnover (Sessions per
  space per day) is below the median turnover of all BPA on-street zones.
- **Quiet zone** (Req 3.11): Morton Ave averages at most 0.40 across its
  Enforcement_Hours.
- **History budget** (Req 20.5): ``generate_history()`` finishes in under 15 s.

Tolerances are fixed by the spec. When a check fails, the fix is to tune the
seed profile parameters (then regenerate ``seed.json``) or the controller
constants in ``sim.py`` -- never to loosen a tolerance here.
"""
from __future__ import annotations

import time as _time
from datetime import timedelta

from app.data import TZ, applicable_rule
from app.sim import BASELINE_FROM_HISTORY, HOURS_PER_WEEK, Simulator, build_simulator

from .conftest import START

# Zone groupings from the seed's zone catalog.
CORE_ZONES = ("bpa-main-st", "bpa-e3rd-west", "bpa-e3rd-east")  # Main St + E 3rd St (core_long)
BPA_ON_STREET = (  # BPA meter zones on street facilities (RapidPark + FlexPark)
    "bpa-main-st", "bpa-e3rd-west", "bpa-e3rd-east", "bpa-e4th", "bpa-new-st", "bpa-morton",
)
MORTON = "bpa-morton"

OUTCOME_TOL_MIN = 5  # Explore Outcome field tolerance (design table)
CURVE_TOL = 0.10  # Req 3.7
CORE_OCCUPANCY_MIN = 0.85  # Req 3.9
MORTON_OCCUPANCY_MAX = 0.40  # Req 3.11
HISTORY_BUDGET_S = 15.0  # Req 20.5


def _enforced_hours_of_week(sim: Simulator, zone_id: str) -> list[int]:
    """Every Hour_Of_Week (0-167) for which the zone has an applicable Rate_Rule.

    Probes each hour at its start minute in America/New_York on a week that
    begins Monday, so the result is independent of the calendar.
    """
    # A known Monday 00:00 local; weekday 0 = Monday.
    monday = START.astimezone(TZ)
    monday = monday - timedelta(days=monday.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    enforced: list[int] = []
    for how in range(HOURS_PER_WEEK):
        probe = monday + timedelta(hours=how)
        if applicable_rule(sim.store, zone_id, probe) is not None:
            enforced.append(how)
    return enforced


def _history_mean_occupancy(sim: Simulator, zone_id: str, hours: list[int]) -> float:
    """Mean of the zone's non-boosted baseline occupancy over the given Hours_Of_Week.

    Only slots backed by real history samples (``baseline_source == "history"``)
    are averaged; curve-fallback slots (every sample boosted) are skipped so the
    check reflects the simulated occupancy, not the prior.
    """
    values = [
        sim.baseline(zone_id, how)
        for how in hours
        if sim.baseline_source(zone_id, how) == BASELINE_FROM_HISTORY
    ]
    assert values, f"{zone_id}: no non-boosted history samples in the requested hours"
    return sum(values) / len(values)


def _turnover_per_space_per_day(sim: Simulator, zone_id: str) -> float:
    """Sessions per space per day over the full history for one zone."""
    capacity = sim.store.zones[zone_id].capacity
    count = sum(1 for s in sim.store.sessions if s.zone_id == zone_id)
    return count / (capacity * sim.history_days)


# Feature: parking-monitor, Calibration: history span (Req 3.1)
def test_history_spans_at_least_28_days_and_ends_at_start(default_sim: Simulator) -> None:
    """Validates: Requirements 3.1"""
    assert default_sim.history_generated
    assert default_sim.history_days >= 28
    span = default_sim.start - default_sim.history_start
    assert span >= timedelta(days=28)
    # The last simulated instant is exactly `start`.
    assert default_sim.simulated_through == default_sim.start


# Feature: parking-monitor, Calibration: Outcome shares (Req 3.5, 3.6)
def test_outcome_shares_match_the_departure_table(default_sim: Simulator) -> None:
    """Validates: Requirements 3.5, 3.6"""
    tol = timedelta(minutes=OUTCOME_TOL_MIN)
    left_early = overstayed = total = 0
    for s in default_sim.store.sessions:
        total += 1
        if s.end_time < s.paid_until - tol:
            left_early += 1
        elif s.end_time > s.paid_until + tol:
            overstayed += 1
    assert total > 0, "no sessions were generated"

    left_early_share = left_early / total
    overstayed_share = overstayed / total
    assert 0.15 <= left_early_share <= 0.40, f"Left Early share {left_early_share:.3f} outside [0.15, 0.40]"
    assert 0.05 <= overstayed_share <= 0.20, f"Overstayed share {overstayed_share:.3f} outside [0.05, 0.20]"


# Feature: parking-monitor, Calibration: per-slot curve tracking (Req 3.7)
def test_mean_occupancy_tracks_the_curve_per_zone_and_hour(default_sim: Simulator) -> None:
    """Validates: Requirements 3.7"""
    offenders: list[str] = []
    for zone_id in default_sim.store.zones:
        curve = default_sim.store.demand_curves[zone_id]
        for how in range(HOURS_PER_WEEK):
            if default_sim.baseline_source(zone_id, how) != BASELINE_FROM_HISTORY:
                continue  # boosted-only slot: no history mean to compare
            mean = default_sim.baseline(zone_id, how)
            if abs(mean - curve[how]) > CURVE_TOL:
                offenders.append(f"{zone_id} h={how}: mean {mean:.3f} vs curve {curve[how]:.3f}")
    assert not offenders, "mean occupancy drifted from the curve:\n" + "\n".join(offenders)


# Feature: parking-monitor, Calibration: core occupancy >= 0.85 (Req 3.9)
def test_core_zones_average_at_least_085_midday_mon_sat(default_sim: Simulator) -> None:
    """Validates: Requirements 3.9"""
    # Hours_Of_Week for 10:00-18:00 (hours 10-17), Monday (0) through Saturday (5).
    hours = [day * 24 + hour for day in range(6) for hour in range(10, 18)]
    for zone_id in CORE_ZONES:
        mean = _history_mean_occupancy(default_sim, zone_id, hours)
        assert mean >= CORE_OCCUPANCY_MIN, (
            f"{zone_id}: midday Mon-Sat occupancy {mean:.3f} below {CORE_OCCUPANCY_MIN}"
        )


# Feature: parking-monitor, Calibration: core turnover below the BPA median (Req 3.10)
def test_core_turnover_below_bpa_on_street_median(default_sim: Simulator) -> None:
    """Validates: Requirements 3.10"""
    turnovers = {zid: _turnover_per_space_per_day(default_sim, zid) for zid in BPA_ON_STREET}
    ordered = sorted(turnovers.values())
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    for zone_id in CORE_ZONES:
        assert turnovers[zone_id] < median, (
            f"{zone_id}: turnover {turnovers[zone_id]:.3f} not below BPA median {median:.3f}"
        )


# Feature: parking-monitor, Calibration: Morton quiet zone <= 0.40 (Req 3.11)
def test_morton_averages_at_most_040_during_enforcement(default_sim: Simulator) -> None:
    """Validates: Requirements 3.11"""
    hours = _enforced_hours_of_week(default_sim, MORTON)
    assert hours, "Morton has no enforced hours"
    mean = _history_mean_occupancy(default_sim, MORTON, hours)
    assert mean <= MORTON_OCCUPANCY_MAX, (
        f"{MORTON}: enforcement-hours occupancy {mean:.3f} above {MORTON_OCCUPANCY_MAX}"
    )


# Feature: parking-monitor, Calibration: history budget (Req 20.5)
def test_generate_history_finishes_under_15_seconds() -> None:
    """Validates: Requirements 20.5"""
    sim = build_simulator(start=START, history_days=28, rng_seed=7)
    started = _time.perf_counter()
    sim.generate_history()
    elapsed = _time.perf_counter() - started
    assert elapsed < HISTORY_BUDGET_S, f"generate_history() took {elapsed:.2f}s, budget {HISTORY_BUDGET_S}s"
