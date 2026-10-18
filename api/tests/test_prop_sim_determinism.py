"""Property 4: Simulation is deterministic for a fixed seed (Req 3.14).

With a configured random seed, the Simulator must produce identical output for
identical random seed, Seed_Data, and start time. Two simulators built
independently from the same ``(rng_seed, start, zone subset)`` must therefore:

- generate the same Session history, session for session, agreeing on the
  published fields ``zone_id``, ``start_time``, ``paid_until``, ``end_time``, and
  ``event_id`` (Req 3.14); and
- hold identical Zone_Status after an identical ``advance_to`` sequence, so the
  live map is reproducible too.

Each example also checks the contrapositive: changing only the seed (same
Seed_Data and start) changes the history, which guards against a simulator that
ignores the seed and would make the equality check vacuous.

All examples use the ``SMALL_ZONES`` subset with a short history so a run is
cheap; the shared ``default_sim`` stays read-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.data import TZ
from app.sim import Simulator, build_simulator

from .conftest import SMALL_ZONES, START

HISTORY_DAYS = 2

# The published Session fields determinism covers. session_id equals the index
# in store.sessions, so comparing the lists positionally also pins the ordering.
_SESSION_FIELDS = ("zone_id", "start_time", "paid_until", "end_time", "event_id")


def _build(rng_seed: int) -> Simulator:
    """A fresh simulator over SMALL_ZONES with history generated, for a given seed."""
    sim = build_simulator(
        start=START,
        history_days=HISTORY_DAYS,
        rng_seed=rng_seed,
        zone_ids=SMALL_ZONES,
    )
    sim.generate_history()
    return sim


def _session_tuples(sim: Simulator) -> list[tuple]:
    """Every session as a tuple of its published fields, in session_id order."""
    return [
        tuple(getattr(s, field) for field in _SESSION_FIELDS)
        for s in sim.store.sessions
    ]


def _status_tuples(sim: Simulator) -> dict[str, tuple]:
    """Each Zone_Status row as the published live-map values, keyed by zone_id."""
    return {
        zid: (row.occupied, row.active_sessions, row.opening_soon, row.updated_at)
        for zid, row in sim.zone_status().items()
    }


# Feature: parking-monitor, Property 4: Simulation is deterministic for a fixed seed
@settings(max_examples=40, deadline=None)
@given(
    seed=st.integers(min_value=0, max_value=50),
    # A shared, monotonically increasing advance_to sequence applied to both
    # simulators; advance_to only moves forward, so the offsets are sorted/unique.
    offsets=st.lists(
        st.integers(min_value=1, max_value=4 * 60 * 60),
        min_size=0,
        max_size=5,
        unique=True,
    ).map(sorted),
)
def test_same_seed_is_deterministic(seed: int, offsets: list[int]) -> None:
    """**Validates: Requirements 3.14**"""
    left = _build(seed)
    right = _build(seed)

    # Req 3.14: identical seed, Seed_Data, and start give identical history.
    assert _session_tuples(left) == _session_tuples(right)

    # The same forward advance_to sequence keeps the live Zone_Status identical.
    for offset in offsets:
        t = (START.astimezone(timezone.utc) + timedelta(seconds=offset)).astimezone(TZ)
        left.advance_to(t)
        right.advance_to(t)
        assert _session_tuples(left) == _session_tuples(right)
        assert _status_tuples(left) == _status_tuples(right)


# Feature: parking-monitor, Property 4: different seeds diverge (guards the equality check)
@settings(max_examples=20, deadline=None)
@given(seed=st.integers(min_value=0, max_value=50), bump=st.integers(min_value=1, max_value=25))
def test_different_seed_changes_history(seed: int, bump: int) -> None:
    """A different random seed (same Seed_Data and start) changes the history.

    This is the contrapositive of Req 3.14: it proves the simulator actually
    consumes the seed, so the same-seed equality above is not vacuous.
    """
    base = _session_tuples(_build(seed))
    other = _session_tuples(_build(seed + bump))
    assert base != other
