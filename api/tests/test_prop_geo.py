"""Property 2: Distance and walk minutes follow the formula.

Covers the geometry half of Property 2: `haversine_m` is non-negative, symmetric,
and zero for identical points, and `walk_minutes` equals ceil(distance x 1.3 / 80).
Task 5.5 checks that the endpoints report `walk_minutes` consistent with `distance_m`.

**Validates: Requirements 8.4, 9.4**
"""
from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from app.data import EARTH_RADIUS_M, haversine_m, walk_minutes

# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #

_finite = {"allow_nan": False, "allow_infinity": False}

# Anywhere on the WGS84 globe.
world_points = st.tuples(
    st.floats(min_value=-90.0, max_value=90.0, **_finite),
    st.floats(min_value=-180.0, max_value=180.0, **_finite),
)

# South Bethlehem / Lehigh, where every seeded Facility and Destination sits.
bethlehem_points = st.tuples(
    st.floats(min_value=40.58, max_value=40.63, **_finite),
    st.floats(min_value=-75.42, max_value=-75.35, **_finite),
)

points = st.one_of(world_points, bethlehem_points)

# Pairs drawn from the same region, so local pairs stay short-range.
point_pairs = st.one_of(
    st.tuples(world_points, world_points),
    st.tuples(bethlehem_points, bethlehem_points),
)

# Any non-negative, finite distance in meters, up to well past half the
# Earth's circumference (~20,015 km).
distances = st.floats(min_value=0.0, max_value=1e9, **_finite)


def _formula(distance_m: float) -> int:
    """Reference Walk_Minutes: distance x 1.3 detour / 80 m per minute, rounded up."""
    return math.ceil(distance_m * 1.3 / 80)


# --------------------------------------------------------------------------- #
# Property tests
# --------------------------------------------------------------------------- #


# Feature: parking-monitor, Property 2: Distance and walk minutes follow the formula
@settings(max_examples=100, deadline=None)
@given(pair=point_pairs)
def test_haversine_is_non_negative_and_symmetric(pair):
    (lat1, lng1), (lat2, lng2) = pair
    d_ab = haversine_m(lat1, lng1, lat2, lng2)
    d_ba = haversine_m(lat2, lng2, lat1, lng1)

    assert math.isfinite(d_ab)
    assert d_ab >= 0.0
    assert math.isclose(d_ab, d_ba, rel_tol=1e-9, abs_tol=1e-6)


# Feature: parking-monitor, Property 2: Distance and walk minutes follow the formula
@settings(max_examples=100, deadline=None)
@given(point=points)
def test_haversine_is_zero_for_identical_points(point):
    lat, lng = point
    assert haversine_m(lat, lng, lat, lng) == 0.0


# Feature: parking-monitor, Property 2: Distance and walk minutes follow the formula
@settings(max_examples=100, deadline=None)
@given(d=distances)
def test_walk_minutes_matches_formula(d):
    minutes = walk_minutes(d)

    assert isinstance(minutes, int)
    assert minutes == _formula(d)
    # The defining bounds of "rounded up to the next whole minute".
    raw = d * 1.3 / 80
    assert minutes - 1 < raw <= minutes
    assert minutes >= 0


# Feature: parking-monitor, Property 2: Distance and walk minutes follow the formula
@settings(max_examples=100, deadline=None)
@given(d1=distances, d2=distances)
def test_walk_minutes_is_monotonic(d1, d2):
    lo, hi = sorted((d1, d2))
    assert walk_minutes(lo) <= walk_minutes(hi)


# Feature: parking-monitor, Property 2: Distance and walk minutes follow the formula
@settings(max_examples=100, deadline=None)
@given(pair=point_pairs)
def test_walk_minutes_of_point_distance_matches_formula(pair):
    (lat1, lng1), (lat2, lng2) = pair
    d = haversine_m(lat1, lng1, lat2, lng2)
    assert walk_minutes(d) == _formula(d)


# --------------------------------------------------------------------------- #
# Explicit examples
# --------------------------------------------------------------------------- #


def test_one_degree_of_latitude_is_about_111_2_km():
    d = haversine_m(40.0, -75.38, 41.0, -75.38)
    assert math.isclose(d, 111_200.0, rel_tol=0.005)


def test_one_degree_of_longitude_at_equator_is_about_111_2_km():
    d = haversine_m(0.0, 0.0, 0.0, 1.0)
    assert math.isclose(d, 111_200.0, rel_tol=0.005)


def test_antipodal_points_are_half_the_circumference():
    d = haversine_m(0.0, 0.0, 0.0, 180.0)
    assert math.isclose(d, math.pi * EARTH_RADIUS_M, rel_tol=1e-9)


def test_walk_minutes_examples():
    assert walk_minutes(0.0) == 0
    assert walk_minutes(100.0) == 2  # 130 / 80 = 1.625 -> 2
    assert walk_minutes(1_000.0) == 17  # 1300 / 80 = 16.25 -> 17
    assert walk_minutes(1_600.0) == 26  # 2080 / 80 = 26.0 exactly
