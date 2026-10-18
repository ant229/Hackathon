"""SpotStack Simulator: synthetic sessions, live advance, and Zone_Status (Req 3, 5).

The Simulator owns the Session table of a `DataStore`. It generates history at
startup, keeps advancing in small live steps while the API runs, and rewrites
every Zone_Status row after each advance (Req 3.1, 3.13, 5.1-5.6).

Time model
----------
- Session timestamps are timezone-aware **UTC** datetimes. UTC keeps
  ``end_time - start_time`` exact across DST (Python subtracts two datetimes
  that share one ``ZoneInfo`` as naive wall times). Convert with
  ``.astimezone(TZ)`` for display; local day and hour always come from TZ.
- ``ZoneStatus.updated_at`` is the update time in America/New_York (display only).
- Internally every instant is an integer of microseconds since the Unix epoch,
  so window, rule-end, and opening-soon comparisons are exact.

Arrival controller (per zone, per step ``[t, t + dt)``)
-------------------------------------------------------
Expire sessions with ``end_time <= t``. If no Rate_Rule applies at ``t``, add
nothing (Req 3.2). Otherwise::

    target = min(0.98, curve[hour_of_week(t)] * event_boost(zone, t))
    lam    = max(0, departures_in_step + 0.5 * min(1, dt / 5 min) * (target * cap - active))
    n      = min(Poisson(lam), cap - active)                    # Req 3.8

Each arrival starts uniformly in ``[t, min(t + dt, rule end))``. Paid duration
(Req 3.3, 3.4): mean ``m = time_limit * dwell_frac`` when the profile has a
``dwell_frac`` and a limit applies, else ``mean_stay_min``; ``x ~ Normal(m,
0.35 m)``; ``paid = 15 * ceil(max(x, 1) / 15)``; cap at the limit; cap at ``15 *
ceil(minutes until rule end / 15)``; floor at 15. Departure (Req 3.5, 3.6):
Left Early 0.25 (``Paid_Until - U(6, max(6, 0.7 paid))`` min, floored at start +
2 min), On Time 0.63 (``Paid_Until - U(0, 5)`` min), Overstayed 0.12
(``Paid_Until + U(6, 30)`` min). A session's Event_ID is the event supplying
the maximum Event_Boost at its start when that boost exceeds 1.0 (Req 3.12).

All randomness comes from ``numpy.random.default_rng(rng_seed)``, and every
iteration order is deterministic, so a fixed seed, Seed_Data, and start give
identical output (Req 3.14).

Prediction (Req 6)
------------------
Every history step records one Estimated_Occupancy sample per zone (12 per
hour) into ``(sum, count)[zone][hour_of_week]`` arrays, skipping samples whose
step start lies inside the Boost_Window of any event impacting the zone (Req
6.1, 6.2). ``sum`` holds the integer Active_Session counts, so the mean sample
``sum / (count * capacity)`` is exact. After history the baselines are computed
once::

    baseline[zone][how] = sum / (count * capacity)   if count > 0  ("history")
                        = demand_curve[zone][how]     otherwise     ("curve")

The curve fallback deviates from the design's "0.0 when there are no samples".
Zoellner performances run every Friday and Saturday, so their Boost_Window
(17:30-23:00) covers every Fri/Sat evening sample for the zones they impact; a
0.0 baseline would predict an empty zone during every show. The demand curve
is the calibrated typical (non-event) occupancy the controller tracks, so it is
the natural prior. ``baseline_source(zone, how)`` tells the two apart.

``predict(zone, t)`` is plain arithmetic (Req 6.3-6.6, no ML library)::

    predicted_occupancy    = min(1, baseline[zone][hour_of_week(t)] * event_boost(zone, t))
    predicted_availability = 1 - predicted_occupancy

Public API
----------
``build_simulator(seed_path, *, start, history_days, rng_seed, step_min, zone_ids)``
loads the seed (optionally restricted to ``zone_ids``), installs events relative
to start's local date, and returns a ``Simulator`` without history.

``Simulator`` methods: ``generate_history()``, ``advance_to(now)``,
``zone_status()``, ``event_boost(zone_id, t)``, ``baseline(zone_id, how)``,
``baseline_source(zone_id, how)``, ``predict(zone_id, t)`` (returns a frozen
``Prediction``), ``opening_soon_counts(t)``, ``add_listener(fn)``.
Attributes: ``store``, ``start``, ``history_start``, ``history_days``, ``step``,
``rng``, ``lock`` (``threading.RLock``), ``zone_ids``, ``zone_index``,
``change_log``; properties ``sessions``, ``simulated_through``,
``history_generated``.

Listeners: ``fn(new_keys, changed_keys)`` is called after ``generate_history()``
and each ``advance_to()`` (and, from task 3.3, each scenario) with the session
keys created and the keys whose ``end_time`` changed since the previous
notification. It is skipped when both lists are empty, runs outside the
simulator lock, and an exception in one listener is logged and does not stop
the others. Keys are ``session_id`` values, which equal the index in
``store.sessions``.

Hooks: ``_record_sample`` (every history step) and ``_finalize_history``
(after history) build the baselines; ``_after_advance`` (task 3.3, scenario
expiry) is still a stub. Helpers: ``_spawn``, ``_end_sessions``, ``_local_rule``,
``_active_count``, ``_opening_soon``, ``_refresh_status``, ``_rebuild_windows``,
and ``_take_notification`` / ``_dispatch``.
"""
from __future__ import annotations

import bisect
import heapq
import logging
import math
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np

from .data import SEED_PATH, TZ, DataStore, Event, Impact, RateRule, Session, ZoneStatus, load_seed
from .events import install_events

__all__ = [
    "BASELINE_FROM_CURVE",
    "BASELINE_FROM_HISTORY",
    "HOURS_PER_WEEK",
    "MAX_TARGET",
    "OPENING_SOON_MIN",
    "OUTCOME_PROBS",
    "BaselineSource",
    "Listener",
    "SCENARIO_RESET",
    "ActiveScenario",
    "Prediction",
    "ScenarioResult",
    "Simulator",
    "UnknownScenario",
    "build_simulator",
    "restrict_zones",
]

log = logging.getLogger(__name__)

UTC: Final = timezone.utc
EPOCH_UTC: Final = datetime(1970, 1, 1, tzinfo=UTC)
ONE_US: Final = timedelta(microseconds=1)
US_PER_MIN: Final = 60_000_000

MAX_TARGET: Final = 0.98  # demand curves never ask for a completely full zone
CONTROLLER_GAIN: Final = 0.5  # share of the occupancy gap closed per 5-minute step
GAIN_REFERENCE_US: Final = 5 * US_PER_MIN
PAY_INCREMENT_MIN: Final = 15
DURATION_SD_FRAC: Final = 0.35
OPENING_SOON_MIN: Final = 15
OPENING_SOON_US: Final = OPENING_SOON_MIN * US_PER_MIN
HOURS_PER_WEEK: Final = 168

# Baseline_Occupancy sources (Req 6.1). A slot with at least one non-boosted
# history sample uses their mean ("history"). A slot with none falls back to the
# zone's demand-curve target for that hour ("curve"), not the design's 0.0:
# weekly events such as Zoellner's Fri/Sat performances cover every sample of
# some slots, and 0.0 there would predict an empty zone during every show.
BaselineSource = Literal["history", "curve"]
BASELINE_FROM_HISTORY: Final = "history"
BASELINE_FROM_CURVE: Final = "curve"
BOOST_LEAD_US: Final = 120 * US_PER_MIN  # Boost_Window opens 2 h before the event starts
BOOST_TAIL_US: Final = 60 * US_PER_MIN  # and closes 1 h after it ends

# Departure table (Req 3.5, 3.6): probabilities of Left Early, On Time, Overstayed.
OUTCOME_PROBS: Final = (0.25, 0.63, 0.12)
LEFT_EARLY_MIN_GAP_MIN: Final = 6.0
LEFT_EARLY_MAX_FRAC: Final = 0.7
MIN_STAY_US: Final = 2 * US_PER_MIN
ON_TIME_MAX_EARLY_MIN: Final = 5.0
OVERSTAY_MIN_MIN: Final = 6.0
OVERSTAY_SPAN_MIN: Final = 24.0  # U(6, 30)

Listener = Callable[[list[int], list[int]], None]

# Demo scenarios (Req 13): injected sessions are always present at the trigger.
SCENARIO_RESET: Final = "reset"
SCENARIO_CAP: Final = 0.95
SCENARIO_LIFT: Final = 0.25
SCENARIO_LOOKBACK_US: Final = 10 * US_PER_MIN
SCENARIO_MIN_PAID_MIN: Final = 45
INJECTED_OUTCOME_PROBS: Final = (0.0, 0.84, 0.16)

AUTO_TAG: Final[Any] = object()  # _spawn sentinel: tag each session from the boost windows


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #


def _check_aware(ts: Any, what: str = "timestamp") -> None:
    if not isinstance(ts, datetime):
        raise TypeError(f"{what} must be a datetime, got {type(ts).__name__}")
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"{what} must be timezone-aware, got naive {ts.isoformat()}")


def _us(ts: datetime) -> int:
    """Microseconds since the Unix epoch for an aware datetime (exact)."""
    return (ts - EPOCH_UTC) // ONE_US


def _dt(us: int) -> datetime:
    """Aware UTC datetime for microseconds since the Unix epoch."""
    return EPOCH_UTC + timedelta(microseconds=us)


def _history_start(start: datetime, history_days: int) -> datetime:
    """History start in UTC: exactly `history_days` x 24 h before `start` (absolute time)."""
    return start.astimezone(UTC) - timedelta(days=history_days)


def _find_rule(rules: tuple[RateRule, ...], minute: int) -> RateRule | None:
    for rule in rules:
        if rule.start_min <= minute < rule.end_min:
            return rule
    return None


# --------------------------------------------------------------------------- #
# Store helpers
# --------------------------------------------------------------------------- #


def restrict_zones(store: DataStore, zone_ids: Iterable[str]) -> DataStore:
    """Keep only `zone_ids` in a freshly loaded store (in place, seed order kept).

    Drops the other zones' Rate_Rules, Zone_Status rows, demand curves, and
    Event_Template impacts, then rebuilds the rule index and validates. Call it
    before events are installed or sessions exist. Raises KeyError for an unknown
    zone and ValueError for an empty subset or a store that already has events or
    sessions.
    """
    keep = set(zone_ids)
    if not keep:
        raise ValueError("zone_ids must name at least one zone")
    unknown = sorted(keep - store.zones.keys())
    if unknown:
        raise KeyError(f"unknown zone_id(s): {', '.join(unknown)}")
    if store.events or store.impacts or store.sessions:
        raise ValueError("restrict_zones must run before events are installed and sessions exist")
    store.zones = {zid: z for zid, z in store.zones.items() if zid in keep}
    store.rate_rules = {rid: r for rid, r in store.rate_rules.items() if r.zone_id in keep}
    store.zone_status = {zid: s for zid, s in store.zone_status.items() if zid in keep}
    store.demand_curves = {zid: c for zid, c in store.demand_curves.items() if zid in keep}
    store.event_templates = [
        {**tpl, "impacts": {zid: b for zid, b in tpl.get("impacts", {}).items() if zid in keep}}
        for tpl in store.event_templates
    ]
    store.rebuild_rule_index()
    store.validate()
    return store


def build_simulator(seed_path: str | Path = SEED_PATH, *, start: datetime, history_days: int = 28,
                    rng_seed: int | None = 7, step_min: int = 5,
                    zone_ids: Iterable[str] | None = None) -> Simulator:
    """Load the seed, install events relative to start's local date, and build a Simulator.

    Events cover ``[start - history_days, local date of start + 28 days]``
    (Req 4.1). History is not generated; call ``generate_history()`` next.
    `zone_ids`, when given, restricts the store to that zone subset (tests).
    """
    _check_aware(start, "start")
    store = load_seed(seed_path)
    if zone_ids is not None:
        restrict_zones(store, zone_ids)
    install_events(store, start.astimezone(TZ).date(), _history_start(start, history_days))
    return Simulator(store, start=start, history_days=history_days, rng_seed=rng_seed, step_min=step_min)


# --------------------------------------------------------------------------- #
# Simulator
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _ZoneParams:
    """Static per-zone inputs, cached so the step loop does no dict lookups."""

    zone_id: str
    capacity: int
    curve: tuple[float, ...]  # 168 target occupancies by Hour_Of_Week
    dwell_frac: float | None
    mean_stay_min: float
    rules: tuple[tuple[RateRule, ...], ...]  # Monday..Sunday, sorted by start_min


# (lo_us, hi_us, demand_boost, event_start_us, event_id), sorted by lo_us
_Window = tuple[int, int, float, int, str]


@dataclass(frozen=True, slots=True)
class Prediction:
    """A zone's predicted occupancy at a time (Req 6.3-6.5, 6.7). Values are unrounded."""

    zone_id: str
    time: datetime  # aware, America/New_York
    hour_of_week: int  # 0-167, Monday 00:00 = 0
    baseline_occupancy: float  # Baseline_Occupancy for (zone, hour_of_week)
    event_boost: float  # max Demand_Boost of windows containing time, else 1.0
    event_name: str | None  # event supplying event_boost; None exactly when event_boost == 1.0
    event_start: datetime | None  # that event's start (America/New_York); None with event_name
    predicted_occupancy: float  # min(1, baseline_occupancy * event_boost)
    predicted_availability: float  # 1 - predicted_occupancy


class UnknownScenario(ValueError):
    """A scenario name outside the seed's scenarios and ``reset`` (Req 13.12)."""

    def __init__(self, name: str, allowed: list[str]) -> None:
        super().__init__(f"Scenario {name!r} is not available.")
        self.name, self.allowed = name, allowed


@dataclass(frozen=True, slots=True)
class ActiveScenario:
    scenario: str
    event_id: str
    event_name: str
    triggered_at: datetime  # America/New_York
    expires_at: datetime
    injected: tuple[int, ...]  # session_ids injected at the trigger


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """What ``apply_scenario`` did (Req 13.6). ``changed`` feeds the live stream."""

    scenario: str
    event: Event | None
    expires_at: datetime | None
    affected: list[dict[str, Any]]
    changed: list[ZoneStatus]


class Simulator:
    """Synthetic session generator and Zone_Status maintainer for one DataStore.

    Construct with a store whose events are already installed and that has no
    sessions (``build_simulator`` does both). Mutating methods hold ``lock``;
    reads that need a consistent view of ``store.sessions`` should hold it too.
    """

    def __init__(self, store: DataStore, *, start: datetime, history_days: int = 28,
                 rng_seed: int | None = 7, step_min: int = 5) -> None:
        _check_aware(start, "start")
        if isinstance(history_days, bool) or not isinstance(history_days, int) or history_days < 0:
            raise ValueError(f"history_days must be a non-negative integer, got {history_days!r}")
        if isinstance(step_min, bool) or not isinstance(step_min, int) or step_min <= 0:
            raise ValueError(f"step_min must be a positive integer, got {step_min!r}")
        if store.sessions:
            raise ValueError("Simulator needs a store without sessions")

        self.store = store
        self.start: datetime = start.astimezone(UTC)
        self.history_days = history_days
        self.history_start: datetime = _history_start(start, history_days)
        self.step = timedelta(minutes=step_min)
        self.rng_seed = rng_seed
        self.rng = np.random.default_rng(rng_seed)
        self.lock = threading.RLock()

        self.zone_ids: tuple[str, ...] = tuple(store.zones)
        self.zone_index: dict[str, int] = {zid: i for i, zid in enumerate(self.zone_ids)}
        self._zones: list[_ZoneParams] = []
        for zid in self.zone_ids:
            zone = store.zones[zid]
            profile = store.profiles[zone.profile]
            dwell = profile.get("dwell_frac")
            self._zones.append(_ZoneParams(
                zone_id=zid,
                capacity=zone.capacity,
                curve=tuple(store.demand_curves[zid]),
                dwell_frac=None if dwell is None else float(dwell),
                mean_stay_min=float(profile["mean_stay_min"]),
                rules=store.rules_by_zone_day[zid],
            ))

        # Per-zone min-heaps of (end_us, session_id) for sessions not yet expired.
        self._heaps: list[list[tuple[int, int]]] = [[] for _ in self.zone_ids]
        self._paid_us: list[int] = []  # paid_until per session_id, in microseconds
        self.change_log: list[int] = []  # append-only: session_ids whose end_time changed
        self._listeners: list[Listener] = []
        self._notified_sessions = 0
        self._notified_changes = 0
        self._clock_us = _us(self.history_start)
        self._history_done = False
        self._local_minute_cache: dict[tuple[date, int], int] = {}
        self._scenario: ActiveScenario | None = None

        self._win: list[list[_Window]] = []
        self._win_lo: list[list[int]] = []
        self._win_span: list[int] = []
        self._rebuild_windows()

        # Baseline accumulators (Req 6.1, 6.2), shape (n_zones, 168): the sum of
        # Active_Session counts and the number of non-boosted samples per slot.
        n_zones = len(self.zone_ids)
        self._capacity = np.array([zp.capacity for zp in self._zones], dtype=np.int64)
        self._bl_sum = np.zeros((n_zones, HOURS_PER_WEEK), dtype=np.int64)
        self._bl_count = np.zeros((n_zones, HOURS_PER_WEEK), dtype=np.int64)
        self._baseline: np.ndarray | None = None  # float64 (n_zones, 168), set by _finalize_history
        self._baseline_from_history: np.ndarray | None = None  # bool (n_zones, 168)

    # ------------------------------------------------------------------ #
    # Read-only views
    # ------------------------------------------------------------------ #

    @property
    def sessions(self) -> list[Session]:
        """The store's Session table; ``sessions[k].session_id == k``. Treat as read-only."""
        return self.store.sessions

    @property
    def simulated_through(self) -> datetime:
        """The simulation clock (UTC): every arrival before this instant has been generated."""
        return _dt(self._clock_us)

    @property
    def history_generated(self) -> bool:
        return self._history_done

    def zone_status(self) -> dict[str, ZoneStatus]:
        """Copies of every Zone_Status row, keyed by zone_id, in seed order."""
        with self.lock:
            return {zid: replace(row) for zid, row in self.store.zone_status.items()}

    def event_boost(self, zone_id: str, t: datetime) -> tuple[float, Event | None]:
        """Event_Boost for a zone at t and the event supplying it (Req 6.3).

        The boost is the largest Demand_Boost among Impacts rows for the zone
        whose Boost_Window (``[start - 2 h, end + 1 h]``, or the event's
        ``window_override``) contains t, both ends inclusive; 1.0 when none does.
        Ties go to the highest boost, then the earliest event start, then the
        event_id. The event is None whenever the boost is 1.0. Raises KeyError for
        an unknown zone and ValueError for a naive t.
        """
        _check_aware(t, "t")
        zi = self.zone_index[zone_id]
        with self.lock:
            boost, event_id = self._boost_at(zi, _us(t))
            return boost, (self.store.events[event_id] if event_id is not None else None)

    def baseline(self, zone_id: str, how: int) -> float:
        """Baseline_Occupancy (0.0-1.0) for a zone and Hour_Of_Week (Req 6.1, 6.2).

        The mean of the zone's non-boosted history samples in that slot, or the
        zone's demand-curve target when the slot has none (see
        ``baseline_source``). Raises KeyError for an unknown zone, ValueError for
        `how` outside 0-167, and RuntimeError before ``generate_history()``.
        """
        zi, how = self._baseline_slot(zone_id, how)
        return float(self._baseline[zi, how])

    def baseline_source(self, zone_id: str, how: int) -> BaselineSource:
        """``"history"`` when the slot's baseline is a mean of samples, ``"curve"`` for the fallback.

        Same errors as ``baseline``.
        """
        zi, how = self._baseline_slot(zone_id, how)
        return BASELINE_FROM_HISTORY if self._baseline_from_history[zi, how] else BASELINE_FROM_CURVE

    def predict(self, zone_id: str, t: datetime) -> Prediction:
        """Predicted occupancy and availability for a zone at t (Req 6.3-6.5, 6.7).

        ``predicted_occupancy = min(1, baseline(zone, hour_of_week(t)) *
        event_boost(zone, t))`` and ``predicted_availability`` is its complement.
        Nothing is rounded. Raises ValueError for a naive t, KeyError for an
        unknown zone, and RuntimeError before ``generate_history()``.
        """
        _check_aware(t, "t")
        local = t.astimezone(TZ)
        how = local.weekday() * 24 + local.hour
        base = self.baseline(zone_id, how)
        boost, event = self.event_boost(zone_id, t)
        occupied = min(1.0, base * boost)
        return Prediction(
            zone_id=zone_id,
            time=local,
            hour_of_week=how,
            baseline_occupancy=base,
            event_boost=boost,
            event_name=event.name if event is not None else None,
            event_start=event.start_time.astimezone(TZ) if event is not None else None,
            predicted_occupancy=occupied,
            predicted_availability=1.0 - occupied,
        )

    def opening_soon_counts(self, t: datetime) -> dict[str, int]:
        """Opening_Soon count per Time_Limited_Zone at t (Req 8.1), in seed order.

        For every zone whose applicable Rate_Rule at t has a time limit, counts
        the Active_Sessions (``start <= t < end_time``) with ``t <= paid_until <=
        t + 15 min``. Time-limited zones with a count of 0 are included; zones
        that are not time-limited at t (no rule, or a rule without a limit) are
        omitted. The API drops the zeros (Req 8.2).

        At or after ``simulated_through`` this scans the per-zone heaps, which hold
        every session still present at the clock, without mutating them; at the
        clock it equals each zone's Zone_Status ``opening_soon``. A t after the
        clock counts only sessions simulated so far. Before the clock it scans the
        whole Session table. Raises ValueError for a naive t.
        """
        _check_aware(t, "t")
        t_us = _us(t)
        hi_us = t_us + OPENING_SOON_US
        with self.lock:
            limited: list[int] = []
            for zi in range(len(self.zone_ids)):
                found = self._local_rule(zi, t)
                if found is not None and found[0].time_limit_min is not None:
                    limited.append(zi)
            if not limited:
                return {}
            counts = dict.fromkeys(limited, 0)
            paid = self._paid_us
            sessions = self.store.sessions
            if t_us >= self._clock_us:
                candidates: Iterable[tuple[int, int]] = (
                    (zi, sid) for zi in limited for _, sid in self._heaps[zi])
            else:
                zone_index = self.zone_index
                candidates = ((zone_index[sessions[sid].zone_id], sid)
                              for sid, p in enumerate(paid) if t_us <= p <= hi_us)
            for zi, sid in candidates:
                if zi not in counts or not t_us <= paid[sid] <= hi_us:
                    continue
                session = sessions[sid]
                if _us(session.start_time) <= t_us < _us(session.end_time):
                    counts[zi] += 1
            return {self.zone_ids[zi]: n for zi, n in counts.items()}

    def _baseline_slot(self, zone_id: str, how: int) -> tuple[int, int]:
        """Validate a (zone, Hour_Of_Week) baseline lookup and return its array indexes."""
        zi = self.zone_index[zone_id]
        if isinstance(how, bool) or not isinstance(how, (int, np.integer)) or not 0 <= how < HOURS_PER_WEEK:
            raise ValueError(f"how must be an integer hour of week from 0 to 167, got {how!r}")
        if self._baseline is None:
            raise RuntimeError("baselines are computed by generate_history(); call it first")
        return zi, int(how)

    def add_listener(self, fn: Listener) -> None:
        """Register ``fn(new_keys, changed_keys)``; see the module docstring for semantics."""
        with self.lock:
            self._listeners.append(fn)

    # ------------------------------------------------------------------ #
    # Driving the simulation
    # ------------------------------------------------------------------ #

    def generate_history(self) -> None:
        """Simulate ``[start - history_days, start)`` in `step` increments (Req 3.1).

        Records one occupancy sample per zone per step through ``_record_sample``,
        calls ``_finalize_history``, sets every Zone_Status row at `start`, and
        notifies listeners. Raises RuntimeError when called twice.
        """
        with self.lock:
            if self._history_done:
                raise RuntimeError("generate_history() has already run")
            end_us = _us(self.start)
            step_us = self.step // ONE_US
            t_us = self._clock_us
            while t_us < end_us:
                nxt = min(t_us + step_us, end_us)
                self._step(t_us, nxt, record=True)
                t_us = nxt
            self._clock_us = end_us
            self._history_done = True
            self._finalize_history()
            self._refresh_status(self.start)
            batch = self._take_notification()
        self._dispatch(batch)

    def advance_to(self, now: datetime) -> list[ZoneStatus]:
        """Simulate ``[simulated_through, now)`` and refresh Zone_Status at `now` (Req 3.13, 5).

        Gaps of any length are split into steps of at most `step`. Returns
        copies of the Zone_Status rows whose ``occupied``, ``active_sessions``,
        or ``opening_soon`` changed; ``updated_at`` moves on every row. A `now` at
        or before ``simulated_through`` changes nothing and returns ``[]``.
        Listeners are notified after the lock is released. Raises RuntimeError
        before ``generate_history()`` and ValueError for a naive `now`.
        """
        _check_aware(now, "now")
        with self.lock:
            if not self._history_done:
                raise RuntimeError("call generate_history() before advance_to()")
            now_us = _us(now)
            if now_us <= self._clock_us:
                return []
            changed = self._advance_locked(now_us)
            batch = self._take_notification()
        self._dispatch(batch)
        return changed

    def _advance_locked(self, now_us: int) -> list[ZoneStatus]:
        """Simulate up to `now_us` (> clock), expire the scenario, refresh Zone_Status. Lock held."""
        step_us = self.step // ONE_US
        t_us = self._clock_us
        while t_us < now_us:
            nxt = min(t_us + step_us, now_us)
            self._step(t_us, nxt, record=False)
            t_us = nxt
        self._clock_us = now_us
        now_utc = _dt(now_us)
        self._after_advance(now_utc)
        return self._refresh_status(now_utc)

    # ------------------------------------------------------------------ #
    # Demo scenarios (Req 13)
    # ------------------------------------------------------------------ #

    def scenario_names(self) -> list[str]:
        return [*self.store.scenarios, SCENARIO_RESET]

    def scenario_status(self, now: datetime) -> dict[str, Any] | None:
        """The active scenario with minutes remaining, or None (also once it has expired)."""
        _check_aware(now, "now")
        with self.lock:
            sc = self._scenario
            if sc is None or now >= sc.expires_at:
                return None
            return {"scenario": sc.scenario, "event_name": sc.event_name,
                    "triggered_at": sc.triggered_at, "expires_at": sc.expires_at,
                    "minutes_remaining": math.ceil((sc.expires_at - now).total_seconds() / 60)}

    def apply_scenario(self, name: str, now: datetime) -> ScenarioResult:
        """Trigger ``game_day``/``family_weekend`` or ``reset`` synchronously (Req 13.2-13.5, 13.9-13.11).

        Simulates up to `now` first, ends any active scenario (its still-present
        injected sessions end at `now`), then, for a real scenario, adds a live
        Event with the template's Impacts and injects sessions so each enforced,
        not-yet-full impacted zone reaches
        ``min(0.95, max(before + 0.25, baseline * boost))``.
        """
        _check_aware(now, "now")
        if name not in self.scenario_names():
            raise UnknownScenario(name, self.scenario_names())
        with self.lock:
            if not self._history_done:
                raise RuntimeError("call generate_history() before apply_scenario()")
            changed: dict[str, ZoneStatus] = {}
            now_us = max(_us(now), self._clock_us)
            if now_us > self._clock_us:
                changed.update((r.zone_id, r) for r in self._advance_locked(now_us))
            now_utc = _dt(now_us)
            rows = self.store.zone_status
            before = {zid: row.occupied for zid, row in rows.items()}
            ended_zones = self._end_scenario(now_utc)

            event: Event | None = None
            expires: datetime | None = None
            affected: list[dict[str, Any]] = []
            if name == SCENARIO_RESET:
                for row in self._refresh_status(now_utc):
                    changed[row.zone_id] = row
                affected = [self._affected(zid, before[zid], None, None) for zid in ended_zones]
            else:
                for row in self._refresh_status(now_utc):
                    changed[row.zone_id] = row
                event, boosts = self._add_live_event(name, now_utc)
                expires = event.end_time
                injected: list[int] = []
                for zid, boost in boosts.items():
                    reason, ids = self._inject(zid, boost, now_us, rows[zid], event.event_id)
                    injected.extend(ids)
                    affected.append((zid, before[zid], boost, reason))
                self._scenario = ActiveScenario(name, event.event_id, event.name, event.start_time,
                                                expires, tuple(injected))
                for row in self._refresh_status(now_utc):
                    changed[row.zone_id] = row
                affected = [self._affected(*a) for a in affected]
            batch = self._take_notification()
        self._dispatch(batch)
        return ScenarioResult(name, event, expires, affected, list(changed.values()))

    def _affected(self, zid: str, before: float, boost: float | None, reason: str | None) -> dict[str, Any]:
        return {"zone_id": zid, "zone_name": self.store.zones[zid].name,
                "occupied_before": round(before, 4),
                "occupied_after": round(self.store.zone_status[zid].occupied, 4),
                "boost": boost if boost is not None else 1.0, "skipped_reason": reason}

    def _end_scenario(self, now: datetime) -> list[str]:
        """Deactivate the active scenario, ending its injected sessions and its Event at `now`.

        Returns the zones that held injected sessions. Lock held.
        """
        sc = self._scenario
        if sc is None:
            return []
        self._scenario = None
        self._end_sessions(sc.injected, now)
        event = self.store.events[sc.event_id]
        if now < event.end_time:
            local = now.astimezone(TZ)
            event.end_time = max(local, event.start_time)
            event.window_override = (event.start_time, event.end_time)
            self._rebuild_windows()
        return list(dict.fromkeys(self.store.sessions[sid].zone_id for sid in sc.injected))

    def _add_live_event(self, name: str, now: datetime) -> tuple[Event, dict[str, float]]:
        """Create the scenario's live Event and copy the template's Impacts (Req 13.2). Lock held."""
        cfg = self.store.scenarios[name]
        tpl = next(t for t in self.store.event_templates if t["template_id"] == cfg["template_id"])
        start = now.astimezone(TZ)
        end = start + timedelta(minutes=int(cfg.get("duration_min", 45)))
        base_id = f"live-{name}-{start:%Y%m%dT%H%M%S}"
        event_id, n = base_id, 1
        while event_id in self.store.events:
            n += 1
            event_id = f"{base_id}-{n}"
        boosts = {zid: float(b) for zid, b in tpl["impacts"].items() if zid in self.zone_index}
        event = Event(event_id, tpl["destination_id"], cfg["event_name"], start, end,
                      int(tpl.get("expected_attendance", 0)), window_override=(start, end))
        self.store.add_events([event], [Impact(event_id, zid, b) for zid, b in boosts.items()])
        self._rebuild_windows()
        return event, boosts

    def _inject(self, zid: str, boost: float, now_us: int, row: ZoneStatus,
                event_id: str) -> tuple[str | None, list[int]]:
        """Inject sessions into one impacted zone (Req 13.3-13.5). Returns (skipped_reason, new ids)."""
        zi = self.zone_index[zid]
        zp = self._zones[zi]
        now = _dt(now_us)
        found = self._local_rule(zi, now)
        if found is None:
            return "not_enforced", []
        if row.occupied >= SCENARIO_CAP:
            return "already_full", []
        rule, rule_start_us, rule_end_us = found
        local = now.astimezone(TZ)
        predicted = min(1.0, self.baseline(zid, local.weekday() * 24 + local.hour) * boost)
        target = min(SCENARIO_CAP, max(row.occupied + SCENARIO_LIFT, predicted))
        target_count = min(math.floor(SCENARIO_CAP * zp.capacity), math.ceil(target * zp.capacity - 1e-9))
        n = min(target_count, zp.capacity) - row.active_sessions
        if n <= 0:
            return None, []
        base_us = max(now_us - SCENARIO_LOOKBACK_US, rule_start_us)
        span_us = max(1, now_us - base_us)
        min_paid = SCENARIO_MIN_PAID_MIN
        if rule.time_limit_min is not None:
            min_paid = min(min_paid, rule.time_limit_min)
        ids = self._spawn(zi, base_us, span_us, n, rule, max(rule_end_us, now_us + min_paid * US_PER_MIN),
                          event_id=event_id, injected=True,
                          outcome_probs=INJECTED_OUTCOME_PROBS, min_paid_min=min_paid)
        return None, ids

    # ------------------------------------------------------------------ #
    # Hooks filled in by later tasks
    # ------------------------------------------------------------------ #

    def _record_sample(self, t: datetime, how: int, active: list[int], in_window: list[bool]) -> None:
        """Task 3.2: record one occupancy sample per zone for history step start `t`.

        `active[i]` is the Active_Session count of ``zone_ids[i]`` at t (start <=
        t < end_time), so the sample is ``active[i] / capacity``. `how` is
        ``hour_of_week(t)``. `in_window[i]` is True when t lies inside the
        Boost_Window of any event impacting that zone (skip those samples, Req 6.2).
        Called with the lock held, once per history step, never in live steps.

        Accumulates the integer active count and a sample count into column `how`
        of ``_bl_sum`` / ``_bl_count`` for the zones outside every window.
        """
        keep = ~np.asarray(in_window, dtype=bool)
        self._bl_sum[:, how] += np.where(keep, np.asarray(active, dtype=np.int64), 0)
        self._bl_count[:, how] += keep

    def _finalize_history(self) -> None:
        """Compute every Baseline_Occupancy once history is complete (lock held, Req 6.1).

        ``sum / (count * capacity)`` where a slot has samples; the zone's demand
        curve for that hour where it has none (module docstring, "Prediction").
        """
        counts = self._bl_count
        has_samples = counts > 0
        curve = np.array([zp.curve for zp in self._zones], dtype=np.float64).reshape(
            len(self._zones), HOURS_PER_WEEK)
        denom = np.where(has_samples, counts * self._capacity[:, None], 1).astype(np.float64)
        means = self._bl_sum / denom
        self._baseline = np.where(has_samples, means, curve)
        self._baseline_from_history = has_samples

    def _after_advance(self, now: datetime) -> None:
        """Deactivate an expired scenario (Req 13.9), ending its injected sessions.

        End the still-present injected sessions at ``expires_at`` (its live Event
        window already closed at expiry, so don't re-touch it) and clear the
        scenario, mirroring ``_end_scenario``'s session handling. Ending at
        ``expires_at`` (not `now`) keeps each End_Time at the real expiry even
        when ``advance_to`` overshoots. Lock held (called from ``_advance_locked``).
        """
        sc = self._scenario
        if sc is not None and now >= sc.expires_at:
            self._scenario = None
            self._end_sessions(sc.injected, sc.expires_at)

    # ------------------------------------------------------------------ #
    # Core step
    # ------------------------------------------------------------------ #

    def _step(self, t_us: int, te_us: int, *, record: bool) -> None:
        """Run the arrival controller for every zone over ``[t_us, te_us)``."""
        t = _dt(t_us)
        local = t.astimezone(TZ)
        weekday = local.weekday()
        minute = local.hour * 60 + local.minute
        how = weekday * 24 + local.hour
        dt_us = te_us - t_us
        gain = CONTROLLER_GAIN * min(1.0, dt_us / GAIN_REFERENCE_US)
        rng = self.rng
        heappop = heapq.heappop
        actives: list[int] = []
        flags: list[bool] = []

        for zi, zp in enumerate(self._zones):
            heap = self._heaps[zi]
            while heap and heap[0][0] <= t_us:  # active means end_time > t
                heappop(heap)
            departing = 0  # sessions still active at t that leave inside the step
            while heap and heap[0][0] < te_us:
                heappop(heap)
                departing += 1
            active = len(heap) + departing

            boost, in_window = (self._window_state(zi, t_us) if self._win[zi] else (1.0, False))
            if record:
                actives.append(active)
                flags.append(in_window)

            rule = _find_rule(zp.rules[weekday], minute)
            if rule is None:
                continue  # arrivals only inside Enforcement_Hours (Req 3.2)
            free = zp.capacity - active
            if free <= 0:
                continue
            target = min(MAX_TARGET, zp.curve[how] * boost)
            lam = departing + gain * (target * zp.capacity - active)
            if lam <= 0.0:
                continue
            n = int(rng.poisson(lam))
            if n > free:
                n = free  # capacity invariant (Req 3.8)
            if n <= 0:
                continue
            rule_end_us = self._local_minute_us(local.date(), rule.end_min)
            span_us = min(dt_us, rule_end_us - t_us)
            self._spawn(zi, t_us, span_us, n, rule, rule_end_us)

        if record:
            self._record_sample(t, how, actives, flags)

    def _spawn(self, zi: int, base_us: int, span_us: int, n: int, rule: RateRule, rule_end_us: int, *,
               event_id: Any = AUTO_TAG, injected: bool = False,
               outcome_probs: tuple[float, float, float] = OUTCOME_PROBS,
               min_paid_min: int = PAY_INCREMENT_MIN) -> list[int]:
        """Create `n` sessions in zone `zi` starting uniformly in ``[base_us, base_us + span_us)``.

        The caller guarantees capacity and that `rule` applies over the whole
        span, which must end at or before `rule_end_us`. Paid duration and End_Time
        follow the module docstring, with the final floor raised to
        `min_paid_min` (a multiple of 15; task 3.3 passes 45 capped by the limit).
        `event_id` defaults to tagging from the boost windows; pass a value
        (including None) to force it. Returns the new session_ids.
        """
        if n <= 0 or span_us <= 0:
            return []
        zp = self._zones[zi]
        limit = rule.time_limit_min
        mean = limit * zp.dwell_frac if (zp.dwell_frac is not None and limit is not None) else zp.mean_stay_min
        sd = DURATION_SD_FRAC * mean
        u_start, u_outcome, u_gap = self.rng.random((3, n)).tolist()
        z = self.rng.standard_normal(n).tolist()
        p_left = outcome_probs[0]
        p_on_time = outcome_probs[0] + outcome_probs[1]
        auto = event_id is AUTO_TAG
        tag = auto and self._overlaps(zi, base_us, base_us + span_us)

        sessions = self.store.sessions
        paid_list = self._paid_us
        heap = self._heaps[zi]
        zone_id = zp.zone_id
        new_ids: list[int] = []
        for k in range(n):
            offset = int(u_start[k] * span_us)
            if offset >= span_us:
                offset = span_us - 1
            start_us = base_us + offset

            x = mean + sd * z[k]
            paid = PAY_INCREMENT_MIN * math.ceil(max(x, 1.0) / PAY_INCREMENT_MIN)
            if limit is not None and paid > limit:
                paid = limit
            end_cap = PAY_INCREMENT_MIN * -(-(rule_end_us - start_us) // (PAY_INCREMENT_MIN * US_PER_MIN))
            if paid > end_cap:
                paid = end_cap  # nobody pays past enforcement
            if paid < min_paid_min:
                paid = min_paid_min
            paid_us = start_us + paid * US_PER_MIN

            uo, ug = u_outcome[k], u_gap[k]
            if uo < p_left:
                hi = max(LEFT_EARLY_MIN_GAP_MIN, LEFT_EARLY_MAX_FRAC * paid)
                gap_min = LEFT_EARLY_MIN_GAP_MIN + ug * (hi - LEFT_EARLY_MIN_GAP_MIN)
                end_us = max(paid_us - int(gap_min * US_PER_MIN), start_us + MIN_STAY_US)
            elif uo < p_on_time:
                end_us = paid_us - int(ON_TIME_MAX_EARLY_MIN * ug * US_PER_MIN)
            else:
                end_us = paid_us + int((OVERSTAY_MIN_MIN + OVERSTAY_SPAN_MIN * ug) * US_PER_MIN)

            if auto:
                eid = self._boost_at(zi, start_us)[1] if tag else None
            else:
                eid = event_id
            sid = len(sessions)
            sessions.append(Session(sid, zone_id, _dt(start_us), _dt(paid_us), _dt(end_us), eid, injected))
            paid_list.append(paid_us)
            heapq.heappush(heap, (end_us, sid))
            new_ids.append(sid)
        return new_ids

    def _end_sessions(self, session_ids: Iterable[int], at: datetime) -> list[int]:
        """Move End_Time to `at` for listed sessions that would still be present after it.

        Logs each changed key in ``change_log`` and rebuilds the affected zones'
        heaps. Returns the changed session_ids. Lock must be held (task 3.3 reset).
        """
        at_us = _us(at)
        sessions = self.store.sessions
        changed: list[int] = []
        zones_touched: set[int] = set()
        for sid in session_ids:
            session = sessions[sid]
            if _us(session.end_time) > at_us:
                session.end_time = _dt(at_us)
                changed.append(sid)
                zones_touched.add(self.zone_index[session.zone_id])
        if changed:
            moved = set(changed)
            for zi in sorted(zones_touched):
                heap = [(at_us, sid) if sid in moved else (end, sid) for end, sid in self._heaps[zi]]
                heapq.heapify(heap)
                self._heaps[zi] = heap
            self.change_log.extend(changed)
        return changed

    # ------------------------------------------------------------------ #
    # Zone_Status
    # ------------------------------------------------------------------ #

    def _active_count(self, zi: int, t_us: int) -> int:
        """Active_Sessions in zone `zi` at `t_us` (expires the heap up to t; t must be >= any earlier call)."""
        heap = self._heaps[zi]
        while heap and heap[0][0] <= t_us:
            heapq.heappop(heap)
        return len(heap)

    def _opening_soon(self, zi: int, t_us: int) -> int:
        """Active sessions with ``t <= paid_until <= t + 15 min`` (call after ``_active_count(zi, t_us)``)."""
        hi = t_us + OPENING_SOON_US
        paid = self._paid_us
        return sum(1 for _, sid in self._heaps[zi] if t_us <= paid[sid] <= hi)

    def _refresh_status(self, t: datetime) -> list[ZoneStatus]:
        """Rewrite every Zone_Status row at t (Req 5.1-5.5); return copies of the changed rows."""
        t_us = _us(t)
        local = t.astimezone(TZ)
        weekday = local.weekday()
        minute = local.hour * 60 + local.minute
        rows = self.store.zone_status
        changed: list[ZoneStatus] = []
        for zi, zp in enumerate(self._zones):
            active = self._active_count(zi, t_us)
            rule = _find_rule(zp.rules[weekday], minute)
            soon = self._opening_soon(zi, t_us) if rule is not None and rule.time_limit_min is not None else 0
            occupied = active / zp.capacity
            row = rows[zp.zone_id]
            is_changed = (row.occupied != occupied or row.active_sessions != active
                          or row.opening_soon != soon)
            row.occupied = occupied
            row.active_sessions = active
            row.opening_soon = soon
            row.updated_at = local
            if is_changed:
                changed.append(replace(row))
        return changed

    # ------------------------------------------------------------------ #
    # Rules and boost windows
    # ------------------------------------------------------------------ #

    def _local_minute_us(self, local_day: date, minute: int) -> int:
        """Instant of local wall time `minute` after midnight of `local_day` (1440 = next midnight), cached."""
        key = (local_day, minute)
        value = self._local_minute_cache.get(key)
        if value is None:
            day = local_day + timedelta(days=minute // 1440)
            rest = minute % 1440
            value = _us(datetime.combine(day, time(rest // 60, rest % 60), tzinfo=TZ))
            self._local_minute_cache[key] = value
        return value

    def _local_rule(self, zi: int, t: datetime) -> tuple[RateRule, int, int] | None:
        """The rule applying in zone `zi` at t with its start and end instants (us), or None."""
        local = t.astimezone(TZ)
        rule = _find_rule(self._zones[zi].rules[local.weekday()], local.hour * 60 + local.minute)
        if rule is None:
            return None
        day = local.date()
        return rule, self._local_minute_us(day, rule.start_min), self._local_minute_us(day, rule.end_min)

    def _rebuild_windows(self) -> None:
        """Rebuild per-zone Boost_Windows from store.events and store.impacts.

        Call after adding or changing events, Impacts, or ``window_override``.
        """
        windows: list[list[_Window]] = [[] for _ in self.zone_ids]
        for (event_id, zone_id), impact in self.store.impacts.items():
            zi = self.zone_index.get(zone_id)
            if zi is None:
                continue
            event = self.store.events[event_id]
            if event.window_override is not None:
                lo_us, hi_us = _us(event.window_override[0]), _us(event.window_override[1])
            else:
                lo_us = _us(event.start_time) - BOOST_LEAD_US
                hi_us = _us(event.end_time) + BOOST_TAIL_US
            windows[zi].append((lo_us, hi_us, impact.demand_boost, _us(event.start_time), event_id))
        for wins in windows:
            wins.sort()
        self._win = windows
        self._win_lo = [[w[0] for w in wins] for wins in windows]
        self._win_span = [max((w[1] - w[0] for w in wins), default=0) for wins in windows]

    def _candidates(self, zi: int, a_us: int, b_us: int) -> range:
        """Indexes of windows that may intersect ``[a_us, b_us]`` (lo within reach of a, lo <= b)."""
        los = self._win_lo[zi]
        return range(bisect.bisect_left(los, a_us - self._win_span[zi]), bisect.bisect_right(los, b_us))

    def _window_state(self, zi: int, t_us: int) -> tuple[float, bool]:
        """(max boost of windows containing t or 1.0, whether any window contains t)."""
        wins = self._win[zi]
        boost, inside = 1.0, False
        for j in self._candidates(zi, t_us, t_us):
            lo, hi, b, _, _ = wins[j]
            if lo <= t_us <= hi:
                inside = True
                if b > boost:
                    boost = b
        return boost, inside

    def _boost_at(self, zi: int, t_us: int) -> tuple[float, str | None]:
        """(Event_Boost, event_id supplying it or None when the boost is 1.0)."""
        wins = self._win[zi]
        if not wins:
            return 1.0, None
        best: tuple[float, int, str] | None = None
        for j in self._candidates(zi, t_us, t_us):
            lo, hi, b, ev_start, eid = wins[j]
            if lo <= t_us <= hi:
                key = (-b, ev_start, eid)
                if best is None or key < best:
                    best = key
        if best is None or -best[0] <= 1.0:
            return 1.0, None
        return -best[0], best[2]

    def _overlaps(self, zi: int, a_us: int, b_us: int) -> bool:
        """True when any window intersects ``[a_us, b_us)``."""
        wins = self._win[zi]
        if not wins:
            return False
        for j in self._candidates(zi, a_us, b_us):
            lo, hi = wins[j][0], wins[j][1]
            if lo < b_us and hi >= a_us:
                return True
        return False

    # ------------------------------------------------------------------ #
    # Listeners
    # ------------------------------------------------------------------ #

    def _take_notification(self) -> tuple[list[Listener], list[int], list[int]] | None:
        """Collect keys since the last notification and advance the cursors (lock held)."""
        n_sessions = len(self.store.sessions)
        n_changes = len(self.change_log)
        new_keys = list(range(self._notified_sessions, n_sessions))
        changed_keys = self.change_log[self._notified_changes:n_changes]
        self._notified_sessions = n_sessions
        self._notified_changes = n_changes
        if not (new_keys or changed_keys) or not self._listeners:
            return None
        return list(self._listeners), new_keys, changed_keys

    @staticmethod
    def _dispatch(batch: tuple[list[Listener], list[int], list[int]] | None) -> None:
        """Call listeners outside the lock; one failing listener doesn't stop the rest."""
        if batch is None:
            return
        listeners, new_keys, changed_keys = batch
        for fn in listeners:
            try:
                fn(new_keys, changed_keys)
            except Exception:  # noqa: BLE001 - a listener bug must not break the simulator
                log.exception("Simulator listener %r failed", fn)
