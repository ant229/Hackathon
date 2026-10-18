"""Shared pytest fixtures for the SpotStack API tests.

Fixtures:

- ``fake_clock`` (function scope): a mutable ``FakeClock`` starting at ``START``,
  a Wednesday afternoon in America/New_York. Call it for the current time,
  ``advance(...)`` to move it forward in absolute time, and ``set(t)`` to jump.
- ``make_clock`` (session scope): a ``FakeClock`` factory, for hypothesis tests
  that can't use function-scoped fixtures.
- ``make_sim`` (session scope): a factory that builds a small simulator, by
  default on the full seed with 2 days of history. Pass ``zones=`` for a subset,
  for example the ``small_zones`` fixture.
- ``small_zones`` (session scope): a representative zone subset, one per profile
  plus event-impacted zones.
- ``default_sim`` (session scope): full seed, 28 days of history, seed 7,
  history generated. Shared by every test, so treat it as read-only: never
  call ``advance_to`` or apply scenarios on it.

API client fixtures live in each test file, so no later task edits this file.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone

import pytest

from app.data import TZ
from app.sim import Simulator, build_simulator

START = datetime(2026, 10, 14, 15, 0, tzinfo=TZ)  # Wednesday 15:00 EDT, inside enforcement everywhere

# One zone per profile, plus zones that football and Zoellner events impact.
SMALL_ZONES = (
    "bpa-e3rd-west",  # core_long, RapidPark, football and Family Weekend impacts
    "bpa-e4th",  # short_stay, RapidPark, Zoellner impacts
    "bpa-morton",  # quiet, FlexPark
    "bpa-new-st-garage",  # garage_commuter
    "lps-farrington",  # visitor_garage, football and Zoellner impacts
    "lps-packer-ave",  # campus_meter, football impacts
    "lps-zoellner-l2",  # permit
)


class FakeClock:
    """A settable aware clock. ``clock()`` returns the current time."""

    def __init__(self, now: datetime = START) -> None:
        self.set(now)

    def __call__(self) -> datetime:
        return self.now

    def set(self, when: datetime) -> datetime:
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError("FakeClock needs a timezone-aware datetime")
        self.now = when.astimezone(TZ)
        return self.now

    def advance(self, delta: timedelta | None = None, **kwargs: float) -> datetime:
        """Move forward by `delta` or ``timedelta(**kwargs)`` in absolute time (DST-safe)."""
        step = delta if delta is not None else timedelta(**kwargs)
        return self.set(self.now.astimezone(timezone.utc) + step)


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture(scope="session")
def make_clock() -> Callable[..., FakeClock]:
    return FakeClock


@pytest.fixture(scope="session")
def small_zones() -> tuple[str, ...]:
    return SMALL_ZONES


@pytest.fixture(scope="session")
def make_sim() -> Callable[..., Simulator]:
    def factory(days: int = 2, zones: Iterable[str] | None = None, rng_seed: int | None = 7,
                start: datetime = START, step_min: int = 5, generate: bool = True) -> Simulator:
        sim = build_simulator(start=start, history_days=days, rng_seed=rng_seed, step_min=step_min,
                              zone_ids=zones)
        if generate:
            sim.generate_history()
        return sim

    return factory


@pytest.fixture(scope="session")
def default_sim() -> Simulator:
    sim = build_simulator(start=START, history_days=28, rng_seed=7)
    sim.generate_history()
    return sim
