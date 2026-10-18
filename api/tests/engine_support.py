"""Shared support for the AssociativeEngine property tests (task 4.2 seam).

Two pieces live here so every engine property test shares one setup:

- ``ListSource``: an in-memory ``SessionSource`` over a fixed list of
  ``SessionRecord`` values. It implements the cursor protocol from
  ``app.sources``: ``sessions_since`` returns the records added after the
  cursor, and ``changed_since`` returns rewritten records. The tests that only
  evaluate selections append everything up front and never change a row, so the
  change log stays empty.
- ``session_records``: a hypothesis strategy that builds lists of
  ``SessionRecord`` over the real seed zones. Start times land inside each
  zone's enforcement window (so a Rate_Rule applies and revenue, Time Limit,
  Arrival Hour, and Day are meaningful), stays and payment windows vary across
  the five Stay_Length and three Outcome buckets, and some records carry a real
  Event_ID so the Event field has more than ``No Event``.

``seed_store`` loads the seed once (restricted to a representative zone subset
with events installed) and ``build_engine`` loads an engine from a record list,
so a test reads: records -> ``build_engine(records)`` -> compare to an oracle.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from hypothesis import strategies as st

from app.associative import AssociativeEngine
from app.data import TZ, DataStore
from app.sim import build_simulator
from app.sources import SessionRecord, SessionSource

from .conftest import SMALL_ZONES, START

__all__ = [
    "ENGINE_ZONES",
    "ListSource",
    "build_engine",
    "seed_store",
    "session_records",
]

# The engine tests run over the same representative subset the simulator tests
# use: one zone per profile, plus the event-impacted zones.
ENGINE_ZONES = SMALL_ZONES

# A window of start times, anchored a little before START, wide enough to cover
# every weekday, every hour, and both event and no-event sessions.
_WINDOW_START = START - timedelta(days=9)
_WINDOW_MINUTES = 9 * 24 * 60


class ListSource:
    """In-memory ``SessionSource`` over a fixed list of records (task 4.2).

    ``records`` are appended in order. ``sessions_since(cursor)`` hands back the
    tail past ``cursor``; ``changed_since`` replays any rewritten records (empty
    for the evaluation tests). Both honor the integer-cursor contract from
    ``app.sources.SessionSource``.
    """

    def __init__(self, records: list[SessionRecord] | None = None) -> None:
        self._records: list[SessionRecord] = list(records or [])
        self._changes: list[tuple[int, SessionRecord]] = []

    def append(self, record: SessionRecord) -> int:
        key = len(self._records)
        self._records.append(record)
        return key

    def change(self, key: int, record: SessionRecord) -> None:
        if not 0 <= key < len(self._records):
            raise ValueError(f"unknown key {key!r}")
        self._records[key] = record
        self._changes.append((key, record))

    def sessions_since(self, cursor: int) -> tuple[list[tuple[int, SessionRecord]], int]:
        end = len(self._records)
        if isinstance(cursor, bool) or not isinstance(cursor, int) or not 0 <= cursor <= end:
            raise ValueError(f"session cursor must be an integer in [0, {end}], got {cursor!r}")
        return [(k, self._records[k]) for k in range(cursor, end)], end

    def changed_since(self, cursor: int) -> tuple[list[tuple[int, SessionRecord]], int]:
        end = len(self._changes)
        if isinstance(cursor, bool) or not isinstance(cursor, int) or not 0 <= cursor <= end:
            raise ValueError(f"change cursor must be an integer in [0, {end}], got {cursor!r}")
        return list(self._changes[cursor:end]), end


# ``ListSource`` must satisfy the SessionSource protocol used by the engine.
assert isinstance(ListSource(), SessionSource)


def seed_store() -> DataStore:
    """Load the seed once over ``ENGINE_ZONES``, with events installed.

    Reuses ``build_simulator`` so Rate_Rules, demand curves, and Events line up
    exactly with the production store. No history is generated: the engine only
    needs the static tables plus Events to resolve field values.
    """
    sim = build_simulator(start=START, history_days=1, rng_seed=7, zone_ids=list(ENGINE_ZONES))
    return sim.store


# One store, reused across examples (loading the seed per example is slow).
_STORE: DataStore | None = None


def _store() -> DataStore:
    global _STORE
    if _STORE is None:
        _STORE = seed_store()
    return _STORE


def build_engine(records: list[SessionRecord], *, history_days: int = 28) -> AssociativeEngine:
    """Build an engine over ``records`` using the shared seed store."""
    engine = AssociativeEngine(_store(), history_days)
    engine.load(ListSource(records))
    return engine


def _event_ids() -> list[str | None]:
    """Event_IDs available over the engine zones, plus ``None`` for No Event."""
    store = _store()
    zones = set(ENGINE_ZONES)
    ids = sorted({eid for (eid, zid) in store.impacts if zid in zones})
    # Weight toward No Event so most sessions fall in the No Event bucket, like
    # real history, while still exercising every tagged event.
    return [None, None, None, *ids]


@st.composite
def _record(draw: st.DrawFn) -> SessionRecord:
    store = _store()
    zone_id = draw(st.sampled_from(list(ENGINE_ZONES)))

    # Start somewhere in the window, rounded to the minute, timezone-aware local.
    minute = draw(st.integers(min_value=0, max_value=_WINDOW_MINUTES))
    start = (_WINDOW_START + timedelta(minutes=minute)).astimezone(TZ)

    # Paid window: 15 min to 5 h, in 15-minute steps, covering every Stay_Length
    # and Time Limit bucket.
    paid_min = draw(st.integers(min_value=1, max_value=20)) * 15
    paid_until = start + timedelta(minutes=paid_min)

    # End relative to paid_until so the three Outcome buckets all appear:
    # well before (Left Early), within the 5-minute grace (On Time), well after
    # (Overstayed).
    outcome_delta = draw(
        st.one_of(
            st.integers(min_value=-120, max_value=-6),  # Left Early
            st.integers(min_value=-4, max_value=4),  # On Time (within grace)
            st.integers(min_value=6, max_value=120),  # Overstayed
        )
    )
    end = paid_until + timedelta(minutes=outcome_delta)
    if end <= start:  # a session must last at least one minute
        end = start + timedelta(minutes=1)

    event_id = draw(st.sampled_from(_event_ids()))
    # Only keep an event tag when it actually impacts this zone, so the Event
    # field value matches what the store can resolve.
    if event_id is not None and (event_id, zone_id) not in store.impacts:
        event_id = None

    return SessionRecord(
        zone_id=zone_id,
        start_time=start,
        paid_until=paid_until,
        end_time=end,
        event_id=event_id,
    )


def session_records(min_size: int = 0, max_size: int = 60) -> st.SearchStrategy[list[SessionRecord]]:
    """A strategy for lists of ``SessionRecord`` over the seed zones."""
    return st.lists(_record(), min_size=min_size, max_size=max_size)
