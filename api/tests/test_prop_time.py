"""Property 1: Hour_Of_Week follows America/New_York local time (Req 1.13)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.data import hour_of_week

NY = ZoneInfo("America/New_York")

# Mix of IANA zones (with and without DST, plus a half-hour offset) and a fixed-offset UTC.
ZONES = [
    timezone.utc,
    ZoneInfo("UTC"),
    NY,
    ZoneInfo("America/Los_Angeles"),
    ZoneInfo("Asia/Tokyo"),
    ZoneInfo("Europe/London"),
    ZoneInfo("Asia/Kolkata"),
]

# US DST transitions for 2025-2027 as UTC instants. Spring forward happens at
# 02:00 EST (07:00 UTC); fall back happens at 02:00 EDT (06:00 UTC).
US_DST_TRANSITIONS_UTC = [
    datetime(2025, 3, 9, 7, tzinfo=timezone.utc),
    datetime(2025, 11, 2, 6, tzinfo=timezone.utc),
    datetime(2026, 3, 8, 7, tzinfo=timezone.utc),
    datetime(2026, 11, 1, 6, tzinfo=timezone.utc),
    datetime(2027, 3, 14, 7, tzinfo=timezone.utc),
    datetime(2027, 11, 7, 6, tzinfo=timezone.utc),
]

zones = st.sampled_from(ZONES)

# Arbitrary aware datetimes across 2025-2027 in any of the zones above.
any_aware = st.datetimes(
    min_value=datetime(2025, 1, 1),
    max_value=datetime(2027, 12, 31, 23, 59, 59),
    timezones=zones,
    allow_imaginary=False,  # wall times skipped by spring-forward don't exist
)

# Instants within three hours of a US DST transition, expressed in any zone.
near_dst = st.builds(
    lambda transition, offset_s, tz: (transition + timedelta(seconds=offset_s)).astimezone(tz),
    st.sampled_from(US_DST_TRANSITIONS_UTC),
    st.integers(min_value=-3 * 3600, max_value=3 * 3600),
    zones,
)


# Feature: parking-monitor, Property 1: Hour-of-week follows America/New_York local time
@settings(max_examples=100, deadline=None)
@given(ts=st.one_of(any_aware, near_dst))
def test_hour_of_week_follows_new_york_local_time(ts: datetime) -> None:
    """**Validates: Requirements 1.13**"""
    local = ts.astimezone(NY)
    how = hour_of_week(ts)
    assert how == local.weekday() * 24 + local.hour
    assert 0 <= how <= 167
    # The same instant expressed in another zone maps to the same slot.
    assert hour_of_week(ts.astimezone(timezone.utc)) == how


@pytest.mark.parametrize(
    "ts",
    [
        datetime(2025, 11, 3, 0, 0),
        datetime(2026, 3, 8, 2, 30),
        datetime(2027, 12, 31, 23, 59, 59),
    ],
)
def test_naive_datetime_raises(ts: datetime) -> None:
    with pytest.raises(ValueError):
        hour_of_week(ts)


@pytest.mark.parametrize(
    ("ts", "expected"),
    [
        # Monday 2025-11-03 00:00 local is the first slot of the week.
        (datetime(2025, 11, 3, 0, 0, tzinfo=NY), 0),
        # Sunday 2025-11-02 23:59 local is the last slot of the week.
        (datetime(2025, 11, 2, 23, 59, tzinfo=NY), 167),
        # Fall back on Sunday 2025-11-02: 01:30 EDT and 01:30 EST share slot 6 * 24 + 1.
        (datetime(2025, 11, 2, 1, 30, tzinfo=NY, fold=0), 145),
        (datetime(2025, 11, 2, 1, 30, tzinfo=NY, fold=1), 145),
        (datetime(2025, 11, 2, 5, 30, tzinfo=timezone.utc), 145),  # 01:30 EDT
        (datetime(2025, 11, 2, 6, 30, tzinfo=timezone.utc), 145),  # 01:30 EST
        # Monday 00:00 New York expressed in Tokyo (14:00 Monday JST).
        (datetime(2025, 11, 3, 14, 0, tzinfo=ZoneInfo("Asia/Tokyo")), 0),
    ],
)
def test_hour_of_week_examples(ts: datetime, expected: int) -> None:
    assert hour_of_week(ts) == expected
