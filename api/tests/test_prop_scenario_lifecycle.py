"""Property 20: Scenario lifecycle keeps at most one scenario active (Req 13.9-13.11).

A demo scenario (``game_day`` or ``family_weekend``) injects sessions and runs
for 45 minutes. The lifecycle rules this test protects:

- **At most one active at a time (Req 13.11).** Triggering a new scenario while
  one is active ends the prior one first: its still-active injected sessions get
  ``end_time = now`` and its live Event ends at ``now``, so the old Event_Boost
  no longer contributes before the new scenario starts.
- **Expiry (Req 13.9).** ``advance_to`` deactivates a scenario once
  ``now >= expires_at``; ``scenario_status`` then returns ``None``, and the
  scenario's Event_Boost no longer contributes to any impacted zone. While a
  scenario is live, ``scenario_status`` reports ``minutes_remaining`` counting
  down to the 45-minute expiry.
- **Reset (Req 13.10).** ``reset`` ends every injected session at the reset time
  and leaves no scenario active.

Each example drives its own small simulator (the shared ``default_sim`` stays
read-only) through a generated sequence of triggers, advances, and resets, and
checks the single-active invariant, the countdown, and correct
expiry/deactivation after every step. The oracle reads ``store.sessions`` and
``event_boost`` directly, never the simulator's scenario bookkeeping.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.data import TZ
from app.sim import Simulator, build_simulator

from .conftest import SMALL_ZONES, START

HISTORY_DAYS = 2
SCENARIO_DURATION_MIN = 45

# game_day and family_weekend both impact zones in SMALL_ZONES, so each trigger
# injects sessions. reset ends whatever is active.
TRIGGER_SCENARIOS = ("game_day", "family_weekend")


def _injected_active(sim: Simulator, t: datetime) -> list[int]:
    """Oracle: session_ids of injected sessions active at t (start <= t < end)."""
    return [
        s.session_id
        for s in sim.store.sessions
        if s.injected and s.start_time <= t < s.end_time
    ]


def _boost_contributes(sim: Simulator, event_id: str, t: datetime) -> bool:
    """True when the given live Event supplies the Event_Boost of any zone it impacts at t."""
    for zone_id in sim.zone_ids:
        boost, event = sim.event_boost(zone_id, t)
        if event is not None and event.event_id == event_id and boost > 1.0:
            return True
    return False


# An action is either a trigger ("game_day"/"family_weekend"), a reset, or an
# advance by a number of minutes. Keep minute gaps small enough that some land
# inside a 45-minute scenario and some land past expiry.
_ACTIONS = st.one_of(
    st.sampled_from(TRIGGER_SCENARIOS).map(lambda s: ("trigger", s)),
    st.just(("reset", None)),
    st.integers(min_value=1, max_value=60).map(lambda m: ("advance", m)),
)


# Feature: parking-monitor, Property 20: Scenario lifecycle keeps at most one scenario active
@settings(max_examples=60, deadline=None)
@given(
    actions=st.lists(_ACTIONS, min_size=1, max_size=12),
    seed=st.integers(min_value=0, max_value=20),
)
def test_scenario_lifecycle_single_active(actions: list[tuple[str, object]], seed: int) -> None:
    """**Validates: Requirements 13.9, 13.10, 13.11**"""
    sim = build_simulator(
        start=START,
        history_days=HISTORY_DAYS,
        rng_seed=seed,
        zone_ids=SMALL_ZONES,
    )
    sim.generate_history()

    # Walk forward in absolute time; advance_to/apply_scenario only move forward.
    now = START.astimezone(timezone.utc) + timedelta(seconds=1)
    # The live Event_ID and expiry of the scenario the test believes is active.
    active_event_id: str | None = None
    active_expires: datetime | None = None

    for action, arg in actions:
        if action == "advance":
            now = now + timedelta(minutes=int(arg))  # type: ignore[arg-type]
            sim.advance_to(now)
        elif action == "trigger":
            now = now + timedelta(minutes=1)
            # A trigger during an active scenario must end the prior injected
            # sessions at the new trigger time (Req 13.11): snapshot them first.
            now_local = now.astimezone(TZ)
            prior_active = _injected_active(sim, now_local)
            result = sim.apply_scenario(str(arg), now)

            # The prior scenario's injected sessions that were still active end at
            # the trigger: none of them is active at or after `now` anymore.
            for sid in prior_active:
                s = sim.store.sessions[sid]
                assert s.end_time <= now_local, (
                    f"prior injected session {sid} still runs past trigger {now_local.isoformat()}"
                )
            # The prior live Event's boost no longer contributes after it ended.
            # Its window closes at the trigger instant (inclusive), so check just
            # after: by then only the new scenario's boost can apply.
            if active_event_id is not None:
                after = (now + timedelta(seconds=1)).astimezone(TZ)
                assert not _boost_contributes(sim, active_event_id, after), (
                    f"prior event {active_event_id} still boosts after new trigger"
                )
            active_event_id = result.event.event_id if result.event is not None else None
            active_expires = result.expires_at
        else:  # reset
            now = now + timedelta(minutes=1)
            now_local = now.astimezone(TZ)
            sim.apply_scenario("reset", now)
            # Req 13.10: every injected session ends at the reset time; none is
            # active at or after the reset, and no scenario is active.
            assert _injected_active(sim, now_local) == [], (
                f"reset at {now_local.isoformat()} left injected sessions active"
            )
            assert sim.scenario_status(now) is None, "reset left a scenario active"
            active_event_id = None
            active_expires = None

        # Invariant after every step: the scenario is active iff now < expires_at.
        now_local = now.astimezone(TZ)
        status = sim.scenario_status(now)
        if active_expires is not None and now < active_expires:
            assert status is not None, "scenario should be active before it expires"
            # minutes_remaining counts down toward the 45-minute expiry.
            remaining = status["minutes_remaining"]
            expected = (active_expires - now).total_seconds() / 60
            assert 0 < remaining <= SCENARIO_DURATION_MIN
            assert remaining - 1 <= expected <= remaining, (
                f"minutes_remaining {remaining} inconsistent with {expected:.2f}"
            )
        else:
            # No scenario, or now is at/after expiry: status is None (Req 13.9)
            # and the expired event's boost no longer contributes anywhere.
            assert status is None, "scenario still active after expiry"
            if active_event_id is not None and active_expires is not None and now >= active_expires:
                # The boost window is inclusive at expires_at, so check strictly
                # after it: past expiry the scenario's boost contributes nowhere.
                if now > active_expires:
                    assert not _boost_contributes(sim, active_event_id, now_local), (
                        f"expired event {active_event_id} still boosts after expiry"
                    )
                active_event_id = None
                active_expires = None
