"""Property 19: Scenario injection reaches its target (Req 13.2-13.6).

This test protects the Game Day demo moment. For any rng seed, trigger time,
and scenario in {game_day, family_weekend}, ``apply_scenario`` must:

- Create a live Event running from the trigger ``now`` to ``now + 45 min``,
  carrying exactly the template's Impacts (zone -> boost), so the live boost
  matches the seed template (Req 13.2).
- For each impacted zone that is enforced at ``now`` with ``occupied_before <
  0.95``: drive the zone to its target, landing within one space (``1 /
  capacity``) of the design formula and never above 0.95 or capacity (Req 13.3):

      predicted    = min(1, baseline * boost)
      target       = min(0.95, max(before + 0.25, predicted))
      target_count = min(floor(0.95 * cap), ceil(target * cap - 1e-9))

- Report a skipped reason for the two skip cases (Req 13.4): ``"already_full"``
  when ``before >= 0.95`` (occupancy unchanged) and ``"not_enforced"`` when no
  Rate_Rule applies at ``now`` (occupancy unchanged).
- Give every session injected at the trigger the live Event_ID, a start inside
  enforcement within the 10 minutes before ``now`` (and at or before ``now``),
  and a paid duration that is a positive multiple of 15 minutes within any
  limit, with the 45-minute floor (Req 13.5). Every injected session is active
  at the trigger (``start <= now < end_time``).
- Return a ``ScenarioResult`` listing, per affected zone, ``zone_id``,
  ``zone_name``, ``occupied_before``, ``occupied_after``, ``boost``, and
  ``skipped_reason`` (Req 13.6).

The oracle recomputes the per-zone target directly from the pre-injection
occupancy, the zone's capacity, and the template boost, and compares it to the
Zone_Status the simulator publishes afterward. Each example builds its own
small simulator (the shared ``default_sim`` stays read-only). The trigger
``now`` stays on START's Wednesday afternoon, inside enforcement for the
football and family-weekend impact zones, so injection actually happens.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.data import TZ, applicable_rule
from app.sim import (
    PAY_INCREMENT_MIN,
    SCENARIO_CAP,
    SCENARIO_LIFT,
    SCENARIO_LOOKBACK_US,
    SCENARIO_MIN_PAID_MIN,
    US_PER_MIN,
    Simulator,
    build_simulator,
)

from .conftest import SMALL_ZONES, START

HISTORY_DAYS = 2
SCENARIOS = ("game_day", "family_weekend")
LOOKBACK = timedelta(microseconds=SCENARIO_LOOKBACK_US)


def _target_count(before: float, baseline: float, boost: float, capacity: int) -> int:
    """Oracle Target_Count from the design formulas (Req 13.3)."""
    predicted = min(1.0, baseline * boost)
    target = min(SCENARIO_CAP, max(before + SCENARIO_LIFT, predicted))
    return min(math.floor(SCENARIO_CAP * capacity), math.ceil(target * capacity - 1e-9))


# Feature: parking-monitor, Property 19: Scenario injection reaches its target
@settings(max_examples=50, deadline=None)
@given(
    scenario=st.sampled_from(SCENARIOS),
    # Trigger time: START's Wednesday afternoon, shifted up to ~90 min so the
    # football and family-weekend impact zones stay inside enforcement and
    # injection actually happens, while baseline occupancy and arrival state vary.
    offset_min=st.integers(min_value=0, max_value=90),
    seed=st.integers(min_value=0, max_value=30),
)
def test_scenario_injection_reaches_target(scenario: str, offset_min: int, seed: int) -> None:
    """**Validates: Requirements 13.2, 13.3, 13.4, 13.5, 13.6**"""
    sim: Simulator = build_simulator(
        start=START,
        history_days=HISTORY_DAYS,
        rng_seed=seed,
        zone_ids=SMALL_ZONES,
    )
    sim.generate_history()

    now = (START.astimezone(timezone.utc) + timedelta(minutes=offset_min)).astimezone(TZ)

    # apply_scenario advances the clock to ``now`` before measuring occupied_before,
    # so advance first and snapshot there to mirror the simulator's own reference.
    if offset_min > 0:
        sim.advance_to(now)

    # Pre-injection state, straight from the simulator's published Zone_Status.
    status_before = sim.zone_status()
    before_occupied = {zid: row.occupied for zid, row in status_before.items()}

    result = sim.apply_scenario(scenario, now)

    # Req 13.2: a live Event runs now -> now + 45 min with the template's Impacts.
    assert result.event is not None
    assert result.expires_at is not None
    assert result.event.start_time == now
    assert result.event.end_time == now + timedelta(minutes=45)
    assert result.expires_at == result.event.end_time

    template = next(
        t for t in sim.store.event_templates if t["template_id"] == sim.store.scenarios[scenario]["template_id"]
    )
    expected_boosts = {zid: float(b) for zid, b in template["impacts"].items() if zid in sim.zone_index}
    live_impacts = {
        zid: imp.demand_boost
        for (eid, zid), imp in sim.store.impacts.items()
        if eid == result.event.event_id
    }
    assert live_impacts == expected_boosts

    status_after = sim.zone_status()
    affected_by_zone = {a["zone_id"]: a for a in result.affected}

    # Req 13.6: exactly the impacted zones are reported, each with the full shape.
    assert set(affected_by_zone) == set(expected_boosts)
    for zid, entry in affected_by_zone.items():
        assert entry["zone_id"] == zid
        assert entry["zone_name"] == sim.store.zones[zid].name
        assert entry["boost"] == expected_boosts[zid]
        assert set(entry) == {
            "zone_id",
            "zone_name",
            "occupied_before",
            "occupied_after",
            "boost",
            "skipped_reason",
        }
        # occupied_before / occupied_after agree with Zone_Status (rounded to 4 dp).
        assert entry["occupied_before"] == round(before_occupied[zid], 4)
        assert entry["occupied_after"] == round(status_after[zid].occupied, 4)

    now_local = now.astimezone(TZ)
    how = now_local.weekday() * 24 + now_local.hour

    for zid, boost in expected_boosts.items():
        entry = affected_by_zone[zid]
        capacity = sim.store.zones[zid].capacity
        before = before_occupied[zid]
        after_row = status_after[zid]
        enforced = applicable_rule(sim.store, zid, now) is not None

        if not enforced:
            # Req 13.4: an unenforced zone is skipped and its occupancy is unchanged.
            assert entry["skipped_reason"] == "not_enforced"
            assert after_row.active_sessions == status_before[zid].active_sessions
            assert after_row.occupied == before
        elif before >= SCENARIO_CAP:
            # Req 13.4: an already-full zone is skipped and its occupancy is unchanged.
            assert entry["skipped_reason"] == "already_full"
            assert after_row.active_sessions == status_before[zid].active_sessions
            assert after_row.occupied == before
        else:
            # Req 13.3: an enforced, not-yet-full zone reaches its target.
            assert entry["skipped_reason"] is None
            baseline = sim.baseline(zid, how)
            target_count = _target_count(before, baseline, boost, capacity)
            # Never exceeds the 0.95 cap or capacity.
            assert after_row.active_sessions <= target_count
            assert after_row.active_sessions <= capacity
            assert after_row.occupied <= SCENARIO_CAP + 1e-9
            # Lands within one space of the target (injection adds target - active,
            # and the target is at least the current active count).
            assert after_row.active_sessions >= status_before[zid].active_sessions
            assert abs(after_row.active_sessions - target_count) <= 1
            assert abs(after_row.occupied - target_count / capacity) <= 1.0 / capacity + 1e-9

    # Req 13.5: every injected session carries the live Event_ID, starts inside
    # enforcement within the 10 minutes before the trigger, pays a multiple of 15
    # minutes within the limit, and is active at the trigger.
    injected = [s for s in sim.store.sessions if s.injected and s.event_id == result.event.event_id]
    injected_zones = {zid for zid, e in affected_by_zone.items() if e["skipped_reason"] is None}
    if injected_zones:
        assert injected, "enforced, not-yet-full zones should have produced injected sessions"
    earliest_start = now - LOOKBACK
    for session in injected:
        assert session.event_id == result.event.event_id
        assert session.zone_id in injected_zones
        # Active at the trigger (On Time or Overstayed only).
        assert session.start_time <= now < session.end_time
        # Started within the 10 minutes before the trigger, inside enforcement.
        assert earliest_start <= session.start_time <= now
        rule = applicable_rule(sim.store, session.zone_id, session.start_time)
        assert rule is not None
        # Paid duration is a positive multiple of 15 minutes within any limit,
        # honouring the 45-minute floor unless the limit is tighter.
        paid_min = round((session.paid_until - session.start_time) / timedelta(minutes=1))
        assert paid_min > 0
        assert paid_min % PAY_INCREMENT_MIN == 0
        floor_min = min(SCENARIO_MIN_PAID_MIN, rule.time_limit_min) if rule.time_limit_min else SCENARIO_MIN_PAID_MIN
        assert paid_min >= floor_min
        if rule.time_limit_min is not None:
            assert paid_min <= rule.time_limit_min
