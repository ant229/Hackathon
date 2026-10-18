"""Event_Template expansion relative to the start date (Req 4).

The seed's `event_templates` describe recurring events. `expand_events` turns them
into concrete Event and Impacts rows for one run of the Analytics_API, always
relative to the date the API starts, so the demo never goes stale (Req 4.5).

Supported rule kinds (all times are local "HH:MM" in America/New_York, and
`day_of_week` 0 = Monday):

- ``alternate_saturdays``: ``{"day_of_week", "interval_days", "start", "end"}``.
  The anchor is the first ``day_of_week`` on or after ``today``; events run on
  ``anchor + k * interval_days`` for every integer k (Req 4.2).
- ``weekly``: ``{"days_of_week", "start", "end"}``. One event on every listed
  weekday (Req 4.3).
- ``single_weekend``: ``{"day_of_week", "anchor_offset_days", "start",
  "end_day_offset", "end"}``. Exactly one event, starting at ``anchor +
  anchor_offset_days`` and ending ``end_day_offset`` days later (Req 4.4).

Times are built as local wall times with ``tzinfo=TZ``, so they stay correct
across DST changes. Event IDs are deterministic: ``f"{template_id}-{YYYY-MM-DD}"``
using the local start date, e.g. ``football-2026-11-07``. Each event gets one
Impacts row per template zone carrying the template's boost (Req 4.6).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Iterable, Mapping

from .data import TZ, DataStore, Event, Impact, parse_hhmm

RULE_KINDS = ("alternate_saturdays", "weekly", "single_weekend")


def _local(day: date, minutes: int) -> datetime:
    """Aware local wall time at `minutes` past midnight of `day` ("24:00" = next midnight)."""
    day = day + timedelta(days=minutes // 1440)
    minutes %= 1440
    return datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=TZ)


def _first_on_or_after(today: date, day_of_week: int) -> date:
    return today + timedelta(days=(day_of_week - today.weekday()) % 7)


def _check_dow(value: Any, tid: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 6:
        raise ValueError(f"event template {tid!r}: day_of_week must be 0-6 (0 = Monday), got {value!r}")
    return value


def _occurrences(tpl: Mapping[str, Any], today: date, lo_date: date, hi_date: date
                 ) -> list[tuple[datetime, datetime]]:
    """(start, end) pairs for one template whose start dates fall in a superset of the window."""
    tid = tpl["template_id"]
    rule = tpl["rule"]
    kind = rule.get("kind")
    try:
        start_min = parse_hhmm(rule["start"])
        end_min = parse_hhmm(rule["end"])
        if kind == "alternate_saturdays":
            interval = rule["interval_days"]
            if isinstance(interval, bool) or not isinstance(interval, int) or interval <= 0:
                raise ValueError(f"event template {tid!r}: interval_days must be a positive integer")
            anchor = _first_on_or_after(today, _check_dow(rule["day_of_week"], tid))
            k_lo = (lo_date - anchor).days // interval
            k_hi = -((anchor - hi_date).days // interval)  # ceil((hi - anchor) / interval)
            days = [anchor + timedelta(days=k * interval) for k in range(k_lo, k_hi + 1)]
            pairs = [(d, d) for d in days]
        elif kind == "weekly":
            wanted = {_check_dow(v, tid) for v in rule["days_of_week"]}
            span = (hi_date - lo_date).days
            days = [lo_date + timedelta(days=i) for i in range(span + 1)]
            pairs = [(d, d) for d in days if d.weekday() in wanted]
        elif kind == "single_weekend":
            anchor = _first_on_or_after(today, _check_dow(rule["day_of_week"], tid))
            start_day = anchor + timedelta(days=rule["anchor_offset_days"])
            pairs = [(start_day, start_day + timedelta(days=rule["end_day_offset"]))]
        else:
            raise ValueError(
                f"event template {tid!r}: unknown rule kind {kind!r}; expected one of {', '.join(RULE_KINDS)}")
    except KeyError as exc:
        raise ValueError(f"event template {tid!r}: rule {kind!r} is missing key {exc.args[0]!r}") from exc

    out = []
    for start_day, end_day in pairs:
        start, end = _local(start_day, start_min), _local(end_day, end_min)
        if end <= start:
            raise ValueError(f"event template {tid!r}: end {rule['end']!r} is not after start {rule['start']!r}")
        out.append((start, end))
    return out


def expand_events(templates: Iterable[Mapping[str, Any]], today: date, history_start: datetime,
                  horizon_days: int = 28) -> tuple[list[Event], list[Impact]]:
    """Expand Event_Templates into Event and Impacts rows (Req 4.1-4.6).

    Covers the interval from `history_start` (aware) through the end of local day
    `today + horizon_days`. An event is included when it overlaps that interval:
    ``end_time > history_start`` and ``start_time < local midnight after today +
    horizon_days``. The anchor dates for alternating and single-weekend rules are
    always computed from `today` (the API's local start date), not from
    `history_start`.

    Returns events sorted by (start_time, event_id) and their Impacts rows in the
    same order, each event's rows in template zone order. Raises ValueError for an
    unknown rule kind (naming it) or a malformed rule, and TypeError when `today`
    is a datetime or `history_start` is naive.
    """
    if isinstance(today, datetime) or not isinstance(today, date):
        raise TypeError(f"today must be a date (local start date), got {type(today).__name__}")
    if not isinstance(history_start, datetime) or history_start.tzinfo is None \
            or history_start.utcoffset() is None:
        raise TypeError("history_start must be a timezone-aware datetime")
    if horizon_days < 0:
        raise ValueError(f"horizon_days must be >= 0, got {horizon_days}")

    window_end = _local(today + timedelta(days=horizon_days + 1), 0)
    # Widen the date range by a day on each side; the overlap test below is exact.
    lo_date = history_start.astimezone(TZ).date() - timedelta(days=1)
    hi_date = today + timedelta(days=horizon_days)

    rows: list[tuple[Event, list[Impact]]] = []
    for tpl in templates:
        tid = tpl["template_id"]
        impacts = tpl.get("impacts", {})
        for start, end in _occurrences(tpl, today, lo_date, hi_date):
            if not (end > history_start and start < window_end):
                continue
            event_id = f"{tid}-{start.date().isoformat()}"
            event = Event(
                event_id=event_id,
                destination_id=tpl["destination_id"],
                name=tpl["name"],
                start_time=start,
                end_time=end,
                expected_attendance=int(tpl["expected_attendance"]),
            )
            rows.append((event, [Impact(event_id, zid, float(boost)) for zid, boost in impacts.items()]))

    rows.sort(key=lambda r: (r[0].start_time, r[0].event_id))
    events = [event for event, _ in rows]
    impacts_out = [impact for _, imps in rows for impact in imps]
    return events, impacts_out


def install_events(store: DataStore, today: date, history_start: datetime, horizon_days: int = 28) -> None:
    """Expand `store.event_templates` and insert the rows with `store.add_events` (atomic, validated)."""
    events, impacts = expand_events(store.event_templates, today, history_start, horizon_days)
    store.add_events(events, impacts)
