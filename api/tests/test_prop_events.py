"""Property 8: Event templates expand on schedule relative to the start date (Req 4.1-4.6).

Uses the real seed templates. Each example picks a start date (`today`) and a
history start 28 days earlier at a varied local time of day, then checks the
expansion against an independent reference schedule. Events are included by
overlap with [history_start, local midnight starting today + 29 days), so an
event straddling either edge still counts.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone

from hypothesis import example, given, settings
from hypothesis import strategies as st

from app.data import TZ, load_seed
from app.events import expand_events, install_events

HORIZON_DAYS = 28
SATURDAY, FRIDAY, SUNDAY = 5, 4, 6

TEMPLATES = {tpl["template_id"]: tpl for tpl in load_seed().event_templates}
assert set(TEMPLATES) == {"football", "zoellner_performance", "family_weekend"}


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _local_at(day: date, hh: int, mm: int) -> datetime:
    return datetime.combine(day, time(hh, mm), tzinfo=TZ)


def _overlaps(start: datetime, end: datetime, lo: datetime, hi: datetime) -> bool:
    return _utc(end) > _utc(lo) and _utc(start) < _utc(hi)


def _wall(ts: datetime) -> tuple[date, int, int]:
    local = ts.astimezone(TZ)
    return local.date(), local.hour, local.minute


# Feature: parking-monitor, Property 8: Event templates expand on schedule relative to the start date
@settings(max_examples=100, deadline=None)
@given(
    today=st.dates(min_value=date(2025, 1, 1), max_value=date(2027, 12, 31)),
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
)
@example(today=date(2026, 11, 7), hour=14, minute=30)  # start date is itself a Saturday
@example(today=date(2026, 3, 8), hour=14, minute=30)  # spring-forward Sunday
@example(today=date(2026, 11, 1), hour=14, minute=30)  # fall-back Sunday
@example(today=date(2025, 1, 1), hour=0, minute=0)
@example(today=date(2027, 12, 31), hour=23, minute=59)
def test_event_templates_expand_on_schedule(today: date, hour: int, minute: int) -> None:
    """**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**"""
    history_start = _local_at(today - timedelta(days=HORIZON_DAYS), hour, minute)
    window_end = _local_at(today + timedelta(days=HORIZON_DAYS + 1), 0, 0)

    events, impacts = expand_events(TEMPLATES.values(), today, history_start, HORIZON_DAYS)

    # Deterministic: an identical call yields identical rows (Req 4.5).
    assert expand_events(TEMPLATES.values(), today, history_start, HORIZON_DAYS) == (events, impacts)

    # Event IDs are unique and derived from the template and local start date.
    ids = [e.event_id for e in events]
    assert len(ids) == len(set(ids))
    by_template: dict[str, list] = defaultdict(list)
    for e in events:
        tid = next((t for t in TEMPLATES if e.event_id == f"{t}-{_wall(e.start_time)[0].isoformat()}"), None)
        assert tid is not None, f"event {e.event_id!r} does not match any template id + local start date"
        tpl = TEMPLATES[tid]
        assert e.name == tpl["name"]
        assert e.destination_id == tpl["destination_id"]
        assert e.expected_attendance == tpl["expected_attendance"]
        assert e.window_override is None
        by_template[tid].append(e)

    # Inclusion is by overlap with the window (Req 4.1).
    for e in events:
        assert e.start_time.tzinfo is not None and e.end_time.tzinfo is not None
        assert _utc(e.end_time) > _utc(e.start_time)
        assert _overlaps(e.start_time, e.end_time, history_start, window_end), e.event_id

    # Every template produces events in a 29-day-plus window (Req 4.1).
    assert set(by_template) == set(TEMPLATES)

    # Football: Saturdays 12:00-16:00 at 14-day spacing from the anchor, the first
    # Saturday on or after the start date (Req 4.2, 4.5).
    anchor = today + timedelta(days=(SATURDAY - today.weekday()) % 7)
    football_days = []
    for e in by_template["football"]:
        start_day, sh, sm = _wall(e.start_time)
        end_day, eh, em = _wall(e.end_time)
        assert start_day.weekday() == SATURDAY and end_day == start_day
        assert (sh, sm, eh, em) == (12, 0, 16, 0)
        assert (start_day - anchor).days % 14 == 0
        football_days.append(start_day)
    assert anchor in football_days, "first Saturday on or after the start date must be a game day"
    k_lo = ((history_start.date() - timedelta(days=1)) - anchor).days // 14
    k_hi = ((window_end.date() - anchor).days // 14) + 1
    expected_football = {
        d for d in (anchor + timedelta(days=14 * k) for k in range(k_lo, k_hi + 1))
        if _overlaps(_local_at(d, 12, 0), _local_at(d, 16, 0), history_start, window_end)
    }
    assert Counter(football_days) == Counter(expected_football)

    # Zoellner: exactly one 19:30-22:00 performance on every Friday and Saturday
    # whose performance overlaps the window (Req 4.3).
    perf_days = []
    for e in by_template["zoellner_performance"]:
        start_day, sh, sm = _wall(e.start_time)
        end_day, eh, em = _wall(e.end_time)
        assert start_day.weekday() in (FRIDAY, SATURDAY) and end_day == start_day
        assert (sh, sm, eh, em) == (19, 30, 22, 0)
        perf_days.append(start_day)
    first = history_start.date() - timedelta(days=1)
    span = (window_end.date() - first).days
    expected_perf = {
        d for d in (first + timedelta(days=i) for i in range(span + 1))
        if d.weekday() in (FRIDAY, SATURDAY)
        and _overlaps(_local_at(d, 19, 30), _local_at(d, 22, 0), history_start, window_end)
    }
    assert Counter(perf_days) == Counter(expected_perf)

    # Family Weekend: exactly one, Saturday 09:00 within 21 days after the start
    # date through the following Sunday 17:00 (Req 4.4).
    assert len(by_template["family_weekend"]) == 1
    fw = by_template["family_weekend"][0]
    start_day, sh, sm = _wall(fw.start_time)
    end_day, eh, em = _wall(fw.end_time)
    assert start_day.weekday() == SATURDAY and (sh, sm) == (9, 0)
    assert 0 < (start_day - today).days <= 21
    assert end_day == start_day + timedelta(days=1) and end_day.weekday() == SUNDAY
    assert (eh, em) == (17, 0)

    # Impacts: one row per template zone carrying the template's boost (Req 4.6).
    event_ids = set(ids)
    rows_by_event: dict[str, list] = defaultdict(list)
    for imp in impacts:
        assert imp.event_id in event_ids
        assert imp.demand_boost >= 1.0
        rows_by_event[imp.event_id].append(imp)
    keys = [(imp.event_id, imp.zone_id) for imp in impacts]
    assert len(keys) == len(set(keys))
    for tid, evs in by_template.items():
        expected_boosts = {zid: float(b) for zid, b in TEMPLATES[tid]["impacts"].items()}
        for e in evs:
            rows = rows_by_event[e.event_id]
            assert len(rows) == len(expected_boosts)
            assert {imp.zone_id: imp.demand_boost for imp in rows} == expected_boosts

    # Installing into a fresh store passes full validation.
    store = load_seed()
    install_events(store, today, history_start, HORIZON_DAYS)
    store.validate()
    assert set(store.events) == event_ids
    assert set(store.impacts) == set(keys)
