"""Property 5: Zone_Status matches a brute-force recount (Req 5.1-5.5).

After the simulator advances to a generated evaluation time ``t``, every
Zone_Status row must agree with a naive Python loop over the whole Session
table:

- ``active_sessions`` is the number of sessions with ``start_time <= t <
  end_time`` in that zone (Req 5.1).
- ``occupied`` is that count divided by the zone's capacity, with no correction
  factor (Req 5.2).
- ``opening_soon`` is, for a Time_Limited_Zone at ``t``, the number of those
  active sessions whose ``paid_until`` lies in ``[t, t + 15 min]`` inclusive
  (Req 5.3), and exactly 0 for a zone that is not time-limited at ``t`` (Req 5.4).
- ``updated_at`` equals ``t`` in America/New_York (Req 5.5).

The oracle never touches the simulator's heaps or cached Zone_Status; it
recomputes every published value directly from ``store.sessions``, so a bug in
the incremental bookkeeping surfaces as a mismatch. Each example builds its own
small simulator (the shared ``default_sim`` stays read-only) and advances it
through a monotonically increasing sequence of evaluation times, checking the
invariant at each one.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.data import TZ, is_time_limited
from app.sim import OPENING_SOON_MIN, Simulator, build_simulator

from .conftest import SMALL_ZONES, START

OPENING_SOON = timedelta(minutes=OPENING_SOON_MIN)
HISTORY_DAYS = 2


def _active_count(sim: Simulator, zone_id: str, t: datetime) -> int:
    """Oracle Active_Sessions: start_time <= t < end_time, scanning the whole table."""
    return sum(
        1
        for s in sim.store.sessions
        if s.zone_id == zone_id and s.start_time <= t < s.end_time
    )


def _opening_soon(sim: Simulator, zone_id: str, t: datetime) -> int:
    """Oracle Opening_Soon: active sessions with t <= paid_until <= t + 15 min, inclusive."""
    hi = t + OPENING_SOON
    return sum(
        1
        for s in sim.store.sessions
        if s.zone_id == zone_id
        and s.start_time <= t < s.end_time
        and t <= s.paid_until <= hi
    )


# Feature: parking-monitor, Property 5: Zone_Status matches a brute-force recount
@settings(max_examples=60, deadline=None)
@given(
    # Monotonically increasing offsets (in seconds) past START; advance_to only
    # moves forward, so the evaluation times must be sorted and distinct.
    offsets=st.lists(
        st.integers(min_value=0, max_value=6 * 60 * 60),
        min_size=1,
        max_size=6,
        unique=True,
    ).map(sorted),
    # Vary the paused start-of-live time within the first evaluation step so the
    # oracle sees a range of occupancy and opening-soon states.
    seed=st.integers(min_value=0, max_value=20),
)
def test_zone_status_matches_brute_force(offsets: list[int], seed: int) -> None:
    """**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**"""
    sim = build_simulator(
        start=START,
        history_days=HISTORY_DAYS,
        rng_seed=seed,
        zone_ids=SMALL_ZONES,
    )
    sim.generate_history()

    for offset in offsets:
        # Evaluation times sit strictly after START (advance_to needs now > clock
        # on the first step), spread across a live window in absolute time.
        t = (START.astimezone(timezone.utc) + timedelta(seconds=offset + 1)).astimezone(TZ)
        sim.advance_to(t)
        status = sim.zone_status()

        for zone_id, row in status.items():
            capacity = sim.store.zones[zone_id].capacity
            expected_active = _active_count(sim, zone_id, t)
            limited = is_time_limited(sim.store, zone_id, t)
            expected_soon = _opening_soon(sim, zone_id, t) if limited else 0

            # Req 5.1: Active_Sessions is the brute-force active count.
            assert row.active_sessions == expected_active, (
                f"{zone_id} active at {t.isoformat()}: "
                f"{row.active_sessions} != {expected_active}"
            )
            # Req 5.2: Occupied is active / capacity, exactly, no correction.
            assert row.occupied == expected_active / capacity, (
                f"{zone_id} occupied at {t.isoformat()}: "
                f"{row.occupied} != {expected_active / capacity}"
            )
            # Req 5.3 / 5.4: Opening_Soon from the oracle, or 0 when not limited.
            assert row.opening_soon == expected_soon, (
                f"{zone_id} opening_soon at {t.isoformat()} "
                f"(time_limited={limited}): {row.opening_soon} != {expected_soon}"
            )
            # Req 5.4: a zone that is not time-limited at t reports exactly 0.
            if not limited:
                assert row.opening_soon == 0
            # Req 5.5: Updated_At is the update time in America/New_York.
            assert row.updated_at == t
