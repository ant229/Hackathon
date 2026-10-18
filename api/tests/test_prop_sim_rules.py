"""Property 3: Generated sessions obey payment rules and capacity (Req 3.2-3.4, 3.8, 3.12).

Every Session the Simulator generates must satisfy the payment and capacity
contract, and the active count in each zone must never exceed capacity:

- 3.2: the Session's ``start_time`` falls inside the Enforcement_Hours of an
  applicable Rate_Rule for its zone, i.e. ``applicable_rule(store, zone_id,
  start_time)`` is not None.
- 3.3: the paid duration ``paid_until - start_time`` is a positive multiple of
  15 minutes.
- 3.4: where the zone is a Time_Limited_Zone at ``start_time``, the paid
  duration is at most the applicable ``time_limit_min``.
- 3.8: at every sampled instant, the count of Active_Sessions
  (``start_time <= t < end_time``) in each zone is at most that zone's capacity.
- 3.12: when the zone's ``event_boost`` at ``start_time`` exceeds 1.0, the
  Session's ``event_id`` is the event supplying that boost.

Each example builds its own small simulator over a few days of history (the
shared ``default_sim`` stays read-only), so the properties cover both the quiet
and the event-boosted stretches that the controller produces. The oracle for
3.2, 3.4, and 3.12 reruns ``applicable_rule`` and ``event_boost`` directly from
the store, so a bug in the controller's own bookkeeping surfaces as a mismatch.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.data import TZ, applicable_rule, is_time_limited
from app.sim import PAY_INCREMENT_MIN, Simulator, build_simulator

from .conftest import SMALL_ZONES, START

PAY_INCREMENT = timedelta(minutes=PAY_INCREMENT_MIN)
HISTORY_DAYS = 3


def _build(seed: int, days: int = HISTORY_DAYS) -> Simulator:
    sim = build_simulator(
        start=START,
        history_days=days,
        rng_seed=seed,
        zone_ids=SMALL_ZONES,
    )
    sim.generate_history()
    return sim


# Feature: parking-monitor, Property 3: Generated sessions obey payment rules and capacity
@settings(max_examples=40, deadline=None)
@given(seed=st.integers(min_value=0, max_value=50))
def test_sessions_obey_rules(seed: int) -> None:
    """**Validates: Requirements 3.2, 3.3, 3.4, 3.12**"""
    sim = _build(seed)
    store = sim.store

    # Every generated session is real history (not a scenario injection here).
    assert store.sessions, "the controller should generate at least one session"

    for s in store.sessions:
        start = s.start_time

        # Req 3.2: Start_Time is inside the Enforcement_Hours of an applicable
        # Rate_Rule for the session's zone.
        rule = applicable_rule(store, s.zone_id, start)
        assert rule is not None, (
            f"session {s.session_id} in {s.zone_id} starts at "
            f"{start.astimezone(TZ).isoformat()} with no applicable rule"
        )

        # Req 3.3: paid duration is a positive multiple of 15 minutes.
        paid = s.paid_until - start
        assert paid > timedelta(0), (
            f"session {s.session_id}: paid duration {paid} is not positive"
        )
        assert paid % PAY_INCREMENT == timedelta(0), (
            f"session {s.session_id}: paid duration {paid} is not a "
            f"multiple of {PAY_INCREMENT_MIN} minutes"
        )

        # Req 3.4: in a Time_Limited_Zone at Start_Time, paid duration <= limit.
        if is_time_limited(store, s.zone_id, start):
            limit = timedelta(minutes=rule.time_limit_min)
            assert paid <= limit, (
                f"session {s.session_id} in {s.zone_id}: paid duration {paid} "
                f"exceeds the {rule.time_limit_min}-minute limit"
            )

        # Req 3.12: when event_boost at Start_Time > 1.0, Event_ID names the
        # event supplying that boost; otherwise there is no event tag.
        boost, event = sim.event_boost(s.zone_id, start)
        if boost > 1.0:
            assert event is not None
            assert s.event_id == event.event_id, (
                f"session {s.session_id} in {s.zone_id}: event_id "
                f"{s.event_id!r} != boosting event {event.event_id!r}"
            )
        else:
            assert s.event_id is None, (
                f"session {s.session_id} in {s.zone_id}: event_id "
                f"{s.event_id!r} set with no boost at start"
            )


# Feature: parking-monitor, Property 3: Generated sessions obey payment rules and capacity
@settings(max_examples=40, deadline=None)
@given(
    seed=st.integers(min_value=0, max_value=50),
    # Sample instants across the history window (in minutes before START), so
    # the capacity invariant is checked over a spread of occupancy states.
    offsets_min=st.lists(
        st.integers(min_value=0, max_value=HISTORY_DAYS * 24 * 60),
        min_size=1,
        max_size=8,
        unique=True,
    ),
)
def test_active_count_never_exceeds_capacity(seed: int, offsets_min: list[int]) -> None:
    """**Validates: Requirements 3.8**"""
    sim = _build(seed)
    store = sim.store
    capacities = {zid: store.zones[zid].capacity for zid in SMALL_ZONES}

    for offset in offsets_min:
        t = (START.astimezone(timezone.utc) - timedelta(minutes=offset)).astimezone(TZ)
        counts = dict.fromkeys(SMALL_ZONES, 0)
        for s in store.sessions:
            if s.start_time <= t < s.end_time:
                counts[s.zone_id] += 1
        for zone_id, count in counts.items():
            assert count <= capacities[zone_id], (
                f"{zone_id} at {t.isoformat()}: {count} active sessions "
                f"exceeds capacity {capacities[zone_id]}"
            )
