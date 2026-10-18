"""Property 6: Baseline excludes boosted samples (Req 6.1, 6.2).

``baseline(zone, h)`` is the historical mean Estimated_Occupancy for one zone
and one Hour_Of_Week, computed from occupancy samples taken at least once per
hour across the Session history, EXCLUDING any sample that falls inside a
Boost_Window (``[event start - 2 h, event end + 1 h]``) of an event that
Impacts the zone.

The oracle re-walks the history the same way the simulator records samples: one
sample per 5-minute step at the step's start instant ``t``, where the sample
value is the zone's Active_Session count at ``t`` (``start_time <= t <
end_time`` over the final Session table, exactly Property 5's recount) divided
by capacity. It drops every sample whose ``t`` lies inside an impacting
Boost_Window (both ends inclusive, matching the simulator's window test), then
averages the survivors per (zone, Hour_Of_Week). A slot with no surviving
samples has an oracle baseline of 0.0 (Req 6.2's "exclude" taken to the limit:
nothing left to average).

The simulator deviates from the design on exactly those empty slots: rather
than publish 0.0 it falls back to the zone's demand curve, because a weekly
event (Zoellner's Friday/Saturday performances) can cover every sample of a
slot and a 0.0 baseline would predict an empty zone during every show. That is
a documented, deliberate choice (``Simulator.baseline`` / ``baseline_source``).
So the property is checked two ways:

- Where the oracle has at least one surviving sample, ``sim.baseline`` must
  equal the oracle mean and report ``baseline_source == "history"``. This is
  the real content of Property 6: boosted samples are excluded and the rest are
  averaged correctly.
- Where the oracle has none (its 0.0 case), ``sim.baseline`` must instead report
  ``baseline_source == "curve"`` and return that zone's demand-curve target,
  confirming the fallback fires exactly on the empty slots.

Each example builds its own small simulator; the shared ``default_sim`` stays
read-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.data import hour_of_week
from app.sim import (
    BASELINE_FROM_CURVE,
    BASELINE_FROM_HISTORY,
    BOOST_LEAD_US,
    BOOST_TAIL_US,
    HOURS_PER_WEEK,
    Simulator,
    build_simulator,
)

from .conftest import SMALL_ZONES, START

STEP = timedelta(minutes=5)
US_PER_MIN = 60_000_000
TOL = 1e-9


def _boost_windows(sim: Simulator) -> dict[str, list[tuple[datetime, datetime]]]:
    """Per-zone Boost_Windows as aware UTC intervals, rebuilt straight from the store.

    For each Impacts row, the window is the event's ``window_override`` when set,
    otherwise ``[start - 2 h, end + 1 h]`` (Req 6.2, Boost_Window). This is an
    independent reconstruction; it does not read the simulator's internal
    window arrays.
    """
    lead = timedelta(microseconds=BOOST_LEAD_US)
    tail = timedelta(microseconds=BOOST_TAIL_US)
    windows: dict[str, list[tuple[datetime, datetime]]] = {zid: [] for zid in sim.store.zones}
    for (event_id, zone_id), _impact in sim.store.impacts.items():
        if zone_id not in windows:
            continue
        event = sim.store.events[event_id]
        if event.window_override is not None:
            lo, hi = event.window_override
        else:
            lo, hi = event.start_time - lead, event.end_time + tail
        windows[zone_id].append((lo.astimezone(timezone.utc), hi.astimezone(timezone.utc)))
    return windows


def _in_any_window(windows: list[tuple[datetime, datetime]], t: datetime) -> bool:
    """True when ``t`` lies in any Boost_Window, both ends inclusive (matches the simulator)."""
    return any(lo <= t <= hi for lo, hi in windows)


def _oracle_baselines(sim: Simulator) -> dict[str, list[float | None]]:
    """Mean non-boosted Estimated_Occupancy per (zone, Hour_Of_Week); None where no sample survives.

    Walks ``[history_start, start)`` in 5-minute steps exactly like
    ``generate_history``. At each step start ``t`` it recounts active sessions
    over the final Session table (Property 5's oracle), skips the sample when
    ``t`` sits inside an impacting Boost_Window, and accumulates the rest.
    """
    windows = _boost_windows(sim)
    sums: dict[str, list[float]] = {zid: [0.0] * HOURS_PER_WEEK for zid in sim.store.zones}
    counts: dict[str, list[int]] = {zid: [0] * HOURS_PER_WEEK for zid in sim.store.zones}

    # Group sessions by zone once so each step's recount is cheap.
    by_zone: dict[str, list] = {zid: [] for zid in sim.store.zones}
    for s in sim.store.sessions:
        by_zone[s.zone_id].append(s)

    t = sim.history_start
    end = sim.start
    while t < end:
        how = hour_of_week(t)
        for zid, zone in sim.store.zones.items():
            if _in_any_window(windows[zid], t):
                continue  # boosted sample excluded (Req 6.2)
            active = sum(1 for s in by_zone[zid] if s.start_time <= t < s.end_time)
            sums[zid][how] += active / zone.capacity
            counts[zid][how] += 1
        t = t + STEP

    means: dict[str, list[float | None]] = {}
    for zid in sim.store.zones:
        means[zid] = [
            (sums[zid][h] / counts[zid][h]) if counts[zid][h] else None
            for h in range(HOURS_PER_WEEK)
        ]
    return means


# Feature: parking-monitor, Property 6: Baseline excludes boosted samples
@settings(max_examples=15, deadline=None)
@given(seed=st.integers(min_value=0, max_value=25))
def test_baseline_excludes_boosted_samples(seed: int) -> None:
    """**Validates: Requirements 6.1, 6.2**"""
    sim = build_simulator(
        start=START,
        history_days=2,
        rng_seed=seed,
        zone_ids=SMALL_ZONES,
    )
    sim.generate_history()

    oracle = _oracle_baselines(sim)

    for zid in sim.store.zones:
        curve = sim.store.demand_curves[zid]
        for how in range(HOURS_PER_WEEK):
            expected = oracle[zid][how]
            actual = sim.baseline(zid, how)
            source = sim.baseline_source(zid, how)

            if expected is not None:
                # Req 6.1 / 6.2: the baseline is the mean of the surviving
                # (non-boosted) samples for this slot.
                assert source == BASELINE_FROM_HISTORY, (
                    f"{zid} h={how}: has {expected!r} samples but source is {source!r}"
                )
                assert abs(actual - expected) <= TOL, (
                    f"{zid} h={how}: baseline {actual} != oracle mean {expected}"
                )
            else:
                # No sample survived the Boost_Window exclusion: the design's 0.0
                # case, where the simulator deliberately falls back to the curve.
                assert source == BASELINE_FROM_CURVE, (
                    f"{zid} h={how}: no surviving sample but source is {source!r}"
                )
                assert abs(actual - curve[how]) <= TOL, (
                    f"{zid} h={how}: fallback {actual} != curve {curve[how]}"
                )
