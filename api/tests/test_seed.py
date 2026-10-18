"""Seed-content example tests for fixtures/seed.json, loaded through app.data.load_seed().

These tests read the committed fixture only. They never run fixtures/build_seed.py,
because that script rewrites seed.json.

Requirements: 1.11, 2.1-2.16, 4.7
"""
from __future__ import annotations

import json

import pytest

from app.data import CURVE_LENGTH, SEED_PATH, DataStore, RateRule, load_seed

ALL_DAYS = tuple(range(7))
MON_SAT = tuple(range(6))

RAPIDPARK_ZONES = ("bpa-main-st", "bpa-e3rd-west", "bpa-e3rd-east", "bpa-e4th")
FLEXPARK_ZONES = ("bpa-new-st", "bpa-morton")
ZOELLNER_PERMIT_LEVELS = ("lps-zoellner-l2", "lps-zoellner-l3", "lps-zoellner-l4")

# Rough South Bethlehem bounding box: catches swapped or non-decimal-degree coordinates.
LAT_RANGE = (40.55, 40.65)
LNG_RANGE = (-75.42, -75.33)


@pytest.fixture(scope="module")
def store() -> DataStore:
    return load_seed()


def rules_for(store: DataStore, zone_id: str) -> list[RateRule]:
    return sorted((r for r in store.rate_rules.values() if r.zone_id == zone_id),
                  key=lambda r: (r.day_of_week, r.start_min))


def zone_by_name(store: DataStore, name: str):
    matches = [z for z in store.zones.values() if z.name == name]
    assert len(matches) == 1, f"expected one zone named {name!r}, found {len(matches)}"
    return matches[0]


def bpa_street_zone_ids(store: DataStore) -> set[str]:
    return {zid for zid in store.zones
            if store.operator_of(zid).operator_id == "bpa" and store.facility_of(zid).type == "street"}


# --------------------------------------------------------------------------- #
# Req 2.1: one JSON file in /fixtures
# --------------------------------------------------------------------------- #


def test_seed_is_one_json_file_in_fixtures():
    assert SEED_PATH.name == "seed.json"
    assert SEED_PATH.parent.name == "fixtures"
    assert SEED_PATH.is_file()
    doc = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert set(doc) == {"operators", "facilities", "zones", "rate_rules", "destinations",
                        "event_templates", "demand_curves", "profiles", "scenarios"}


def test_seed_has_fifteen_zones_each_with_status(store):
    assert len(store.zones) == 15
    assert set(store.zone_status) == set(store.zones)


# --------------------------------------------------------------------------- #
# Req 2.2: operators and pay apps
# --------------------------------------------------------------------------- #


def test_operators_and_pay_apps(store):
    assert set(store.operators) == {"bpa", "lps"}
    bpa, lps = store.operators["bpa"], store.operators["lps"]
    assert bpa.name == "Bethlehem Parking Authority"
    assert set(bpa.pay_app) == {"ParkMobile", "PayByPhone"}
    assert lps.name == "Lehigh Parking Services"
    assert lps.pay_app == ("Passport Parking",)


# --------------------------------------------------------------------------- #
# Req 2.3, 2.4: RapidPark and FlexPark rules
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("zone_ids", "label", "rate", "limit"), [
    (RAPIDPARK_ZONES, "RapidPark", 2.5, 120),
    (FLEXPARK_ZONES, "FlexPark", 1.5, 180),
])
def test_bpa_meter_rules(store, zone_ids, label, rate, limit):
    named = {z.zone_id for z in store.zones.values() if label in z.name}
    assert named == set(zone_ids)
    for zid in zone_ids:
        assert zid in bpa_street_zone_ids(store)
        rules = rules_for(store, zid)
        assert [r.day_of_week for r in rules] == list(MON_SAT), zid
        for rule in rules:
            assert rule.hourly_rate == pytest.approx(rate), rule.rule_id
            assert rule.time_limit_min == limit, rule.rule_id
            assert (rule.start_min, rule.end_min) == (8 * 60, 21 * 60), rule.rule_id
        assert store.rules_by_zone_day[zid][6] == (), f"{zid} has a Sunday rule"


# --------------------------------------------------------------------------- #
# Req 2.5, 2.6: BPA on-street notes and calibration-target zones
# --------------------------------------------------------------------------- #


def test_bpa_street_zones_note_pay_stations_and_apps(store):
    street = bpa_street_zone_ids(store)
    assert street == set(RAPIDPARK_ZONES) | set(FLEXPARK_ZONES)
    for zid in street:
        note = store.zones[zid].note
        assert note, f"{zid} has no note"
        assert "pay station" in note.lower(), zid
        assert "ParkMobile" in note and "PayByPhone" in note, zid


@pytest.mark.parametrize(("facility_name", "zone_ids"), [
    ("Main Street Meters", {"bpa-main-st"}),
    ("East 3rd Street Meters", {"bpa-e3rd-west", "bpa-e3rd-east"}),
    ("Morton Avenue Meters", {"bpa-morton"}),
])
def test_bpa_calibration_target_streets(store, facility_name, zone_ids):
    found = {zid for zid in bpa_street_zone_ids(store)
             if store.facility_of(zid).name == facility_name}
    assert found == zone_ids


# --------------------------------------------------------------------------- #
# Req 2.7: BPA garages
# --------------------------------------------------------------------------- #


def test_polk_street_garage_capacity(store):
    zone = zone_by_name(store, "Polk Street Garage")
    assert zone.capacity == 731
    facility = store.facility_of(zone.zone_id)
    assert facility.type == "garage"
    assert facility.operator_id == "bpa"


def test_new_street_garage_address(store):
    zone = zone_by_name(store, "New Street Garage")
    facility = store.facility_of(zone.zone_id)
    assert facility.type == "garage"
    assert facility.operator_id == "bpa"
    assert "324 South New Street" in (zone.note or "")


# --------------------------------------------------------------------------- #
# Req 2.8, 2.9: Zoellner Garage levels
# --------------------------------------------------------------------------- #


def test_zoellner_level_1_visitor_rules(store):
    zone = store.zones["lps-zoellner-l1"]
    assert zone.name == "Zoellner Garage Level 1"
    assert zone.visitor_allowed is True
    assert store.operator_of(zone.zone_id).operator_id == "lps"
    rules = rules_for(store, zone.zone_id)
    assert [r.day_of_week for r in rules] == list(ALL_DAYS)
    for rule in rules:
        assert rule.hourly_rate == pytest.approx(1.0), rule.rule_id
        assert rule.end_min == 23 * 60, rule.rule_id
        # The 07:00 start hour is unverified, so the rule stays a placeholder.
        assert rule.placeholder is True, rule.rule_id


@pytest.mark.parametrize("zone_id", ZOELLNER_PERMIT_LEVELS)
def test_zoellner_levels_2_to_4_are_permit_only(store, zone_id):
    zone = store.zones[zone_id]
    level = zone_id[-1]
    assert zone.name == f"Zoellner Garage Level {level}"
    assert zone.visitor_allowed is False
    assert zone.facility_id == store.zones["lps-zoellner-l1"].facility_id
    assert store.operator_of(zone_id).operator_id == "lps"


# --------------------------------------------------------------------------- #
# Req 2.10, 2.11: Farrington Square lower level
# --------------------------------------------------------------------------- #


def test_farrington_zone_and_rules(store):
    zone = store.zones["lps-farrington"]
    assert "Farrington Square" in zone.name
    assert "Lower Level" in zone.name
    assert zone.capacity == 52
    assert zone.visitor_allowed is True
    assert store.operator_of(zone.zone_id).operator_id == "lps"
    rules = rules_for(store, zone.zone_id)
    assert [r.day_of_week for r in rules] == list(ALL_DAYS)
    for rule in rules:
        assert rule.hourly_rate == pytest.approx(1.0), rule.rule_id
        assert (rule.start_min, rule.end_min) == (6 * 60, 24 * 60), rule.rule_id


def test_farrington_note_mentions_text2park(store):
    note = store.zones["lps-farrington"].note or ""
    assert "Text2Park" in note
    assert "16:00" in note or "4 PM" in note
    assert "weekend" in note.lower()


# --------------------------------------------------------------------------- #
# Req 2.12: Lehigh Parking Services meters paid through Passport Parking
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("zone_id", "facility_name"), [
    ("lps-packer-ave", "Packer Avenue Meters"),
    ("lps-alumni-l1", "Alumni Garage"),
])
def test_lps_meter_zones(store, zone_id, facility_name):
    zone = store.zones[zone_id]
    assert store.facility_of(zone_id).name == facility_name
    operator = store.operator_of(zone_id)
    assert operator.operator_id == "lps"
    assert "Passport Parking" in operator.pay_app
    assert "Passport Parking" in (zone.note or "")
    assert rules_for(store, zone_id), f"{zone_id} has no rate rules"
    if zone_id == "lps-alumni-l1":
        assert "Level 1" in zone.name


# --------------------------------------------------------------------------- #
# Req 2.13, 2.14: placeholder and source flags
# --------------------------------------------------------------------------- #


def test_non_placeholder_rules_have_a_source(store):
    for rule in store.rate_rules.values():
        if not rule.placeholder:
            assert isinstance(rule.source, str) and rule.source.strip(), rule.rule_id


def test_placeholder_flags_match_design_catalog(store):
    verified = set(RAPIDPARK_ZONES) | set(FLEXPARK_ZONES) | {"lps-farrington"}
    for rule in store.rate_rules.values():
        assert rule.placeholder is (rule.zone_id not in verified), rule.rule_id


# --------------------------------------------------------------------------- #
# Req 1.11, 2.15: destinations and WGS84 positions
# --------------------------------------------------------------------------- #


def test_four_destinations_with_positions(store):
    names = {d.name for d in store.destinations.values()}
    assert names == {"Zoellner Arts Center", "Goodman Stadium", "Alumni Memorial Building",
                     "3rd Street shops"}
    for dest in store.destinations.values():
        assert isinstance(dest.lat, float) and isinstance(dest.lng, float), dest.destination_id
        assert LAT_RANGE[0] <= dest.lat <= LAT_RANGE[1], dest.destination_id
        assert LNG_RANGE[0] <= dest.lng <= LNG_RANGE[1], dest.destination_id


def test_facility_positions_are_decimal_degrees(store):
    for fac in store.facilities.values():
        assert isinstance(fac.lat, float) and isinstance(fac.lng, float), fac.facility_id
        assert LAT_RANGE[0] <= fac.lat <= LAT_RANGE[1], fac.facility_id
        assert LNG_RANGE[0] <= fac.lng <= LNG_RANGE[1], fac.facility_id


# --------------------------------------------------------------------------- #
# Req 2.16: demand curves
# --------------------------------------------------------------------------- #


def test_every_zone_has_a_168_value_demand_curve(store):
    assert CURVE_LENGTH == 168
    assert set(store.demand_curves) == set(store.zones)
    for zid, curve in store.demand_curves.items():
        assert len(curve) == 168, zid
        assert all(0.0 <= v <= 0.98 for v in curve), zid
        assert max(curve) > 0.0, f"{zid} curve is all zeros"


# --------------------------------------------------------------------------- #
# Req 4.7: event template boosts
# --------------------------------------------------------------------------- #


def test_event_template_boosts_reference_zones_and_are_at_least_one(store):
    assert {t["template_id"] for t in store.event_templates} == {
        "football", "zoellner_performance", "family_weekend"}
    for tpl in store.event_templates:
        assert tpl["impacts"], f"{tpl['template_id']} lists no zones"
        for zid, boost in tpl["impacts"].items():
            assert zid in store.zones, (tpl["template_id"], zid)
            assert boost >= 1.0, (tpl["template_id"], zid, boost)
