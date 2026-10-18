"""Generate fixtures/seed.json, the shared SpotStack seed fixture.

Run from the workspace root (standard library only):

    python3 fixtures/build_seed.py

Output is byte-for-byte deterministic: fixed key order, fixed rounding, and no
clock or randomness. The script validates the document before writing it and
exits non-zero if any check fails.

Document keys: operators, facilities, zones, rate_rules, destinations,
event_templates, demand_curves, profiles, scenarios.

Formats
- Times are "HH:MM" local America/New_York strings; "24:00" means end of day.
- day_of_week uses 0 = Monday ... 6 = Sunday (Postgres ISODOW - 1).
- Hour_Of_Week = day_of_week * 24 + hour, so demand curves have 168 values.
- lat/lng are WGS84 decimal degrees (Req 1.11).

Calibration and placeholders
- Rate rules with "placeholder": false carry a "source" string (Req 2.13, 2.14).
  Zoellner Level 1 is a placeholder because its 07:00 start hour is unverified;
  its source string names the verified part.
- Capacities are placeholders except Polk Street Garage (731) and Farrington
  Square Lower Level (52). Coordinates are approximate.

Profiles drive the simulator's paid duration (design "Paid duration", step 1):
- dwell_frac set and a time limit applies: mean = time_limit_min * dwell_frac.
- Otherwise (dwell_frac is null, or no limit applies): mean = mean_stay_min.
  The draw is still capped at the time limit and at the end of enforcement.

Demand curves follow three shaping rules (design "Seed Fixture"):
1. Unenforced hours are 0.0, except the first hour after enforcement ends,
   which is 0.1 x the previous hour.
2. The first enforced hour is at most 0.40.
3. Consecutive enforced hours differ by at most 0.15 (MAX_STEP keeps a small
   margin so float comparisons against 0.15 stay safe).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).with_name("seed.json")

MON_SAT = (0, 1, 2, 3, 4, 5)
MON_FRI = (0, 1, 2, 3, 4)
ALL_DAYS = (0, 1, 2, 3, 4, 5, 6)
DAY_ABBR = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Curve shaping, in thousandths so every value is exact before conversion.
FIRST_HOUR_MAX = 400      # rule 2: first enforced hour <= 0.40
MAX_STEP = 145            # rule 3: consecutive enforced hours differ by <= 0.15
TARGET_MAX = 980          # simulator target cap is 0.98
POST_ENFORCEMENT_DIVISOR = 10_000  # rule 1: thousandths * 0.1, expressed exactly

BPA_STREET_NOTE = "Pay stations accepted in addition to the ParkMobile and PayByPhone apps."
PERMIT_NOTE = "Permit holders only. Visitors use Level 1."
PASSPORT_NOTE = "Pay with the Passport Parking app."

# --------------------------------------------------------------------------- #
# Operators and facilities
# --------------------------------------------------------------------------- #

OPERATORS = [
    {"operator_id": "bpa", "name": "Bethlehem Parking Authority", "pay_app": ["ParkMobile", "PayByPhone"]},
    {"operator_id": "lps", "name": "Lehigh Parking Services", "pay_app": ["Passport Parking"]},
]

FACILITIES = [
    {"facility_id": "fac-main-st-meters", "operator_id": "bpa", "name": "Main Street Meters",
     "type": "street", "lat": 40.6196, "lng": -75.3822},
    {"facility_id": "fac-e3rd-st-meters", "operator_id": "bpa", "name": "East 3rd Street Meters",
     "type": "street", "lat": 40.6128, "lng": -75.3772},
    {"facility_id": "fac-e4th-st-meters", "operator_id": "bpa", "name": "East 4th Street Meters",
     "type": "street", "lat": 40.611, "lng": -75.3768},
    {"facility_id": "fac-new-st-meters", "operator_id": "bpa", "name": "New Street Meters",
     "type": "street", "lat": 40.6124, "lng": -75.3792},
    {"facility_id": "fac-morton-ave-meters", "operator_id": "bpa", "name": "Morton Avenue Meters",
     "type": "street", "lat": 40.6094, "lng": -75.3752},
    {"facility_id": "fac-polk-st-garage", "operator_id": "bpa", "name": "Polk Street Garage",
     "type": "garage", "lat": 40.6131, "lng": -75.3738},
    {"facility_id": "fac-new-st-garage", "operator_id": "bpa", "name": "New Street Garage",
     "type": "garage", "lat": 40.6116, "lng": -75.3786},
    {"facility_id": "fac-zoellner-garage", "operator_id": "lps", "name": "Zoellner Garage",
     "type": "garage", "lat": 40.6086, "lng": -75.3734},
    {"facility_id": "fac-farrington-garage", "operator_id": "lps", "name": "Farrington Square Garage",
     "type": "garage", "lat": 40.6101, "lng": -75.3784},
    {"facility_id": "fac-packer-ave-meters", "operator_id": "lps", "name": "Packer Avenue Meters",
     "type": "street", "lat": 40.6079, "lng": -75.3765},
    {"facility_id": "fac-alumni-garage", "operator_id": "lps", "name": "Alumni Garage",
     "type": "garage", "lat": 40.6062, "lng": -75.3812},
]

# --------------------------------------------------------------------------- #
# Rate rule sets: one rule per listed day, expanded per zone
# --------------------------------------------------------------------------- #

RULE_SETS = {
    "rapidpark": {"days": MON_SAT, "start": "08:00", "end": "21:00", "hourly_rate": 2.5,
                  "time_limit_min": 120, "placeholder": False,
                  "source": "ParkBethlehem RapidPark rates (bethpark.org)"},
    "flexpark": {"days": MON_SAT, "start": "08:00", "end": "21:00", "hourly_rate": 1.5,
                 "time_limit_min": 180, "placeholder": False,
                 "source": "ParkBethlehem FlexPark rates (bethpark.org)"},
    "bpa_garage": {"days": ALL_DAYS, "start": "06:00", "end": "24:00", "hourly_rate": 1.0,
                   "time_limit_min": None, "placeholder": True, "source": None},
    "zoellner_visitor": {"days": ALL_DAYS, "start": "07:00", "end": "23:00", "hourly_rate": 1.0,
                         "time_limit_min": None, "placeholder": True,
                         "source": "Lehigh Parking Services visitor parking, $1.00 per hour until 11 PM "
                                   "(parking.lehigh.edu); 07:00 start hour unverified"},
    "zoellner_permit": {"days": MON_FRI, "start": "07:00", "end": "17:00", "hourly_rate": 0.0,
                        "time_limit_min": None, "placeholder": True, "source": None},
    "farrington": {"days": ALL_DAYS, "start": "06:00", "end": "24:00", "hourly_rate": 1.0,
                   "time_limit_min": None, "placeholder": False,
                   "source": "Lehigh Parking Services, Farrington Square garage visitor parking "
                             "(parking.lehigh.edu)"},
    "campus_meter": {"days": MON_FRI, "start": "07:00", "end": "17:00", "hourly_rate": 1.0,
                     "time_limit_min": 120, "placeholder": True, "source": None},
}

# --------------------------------------------------------------------------- #
# Zone catalog (design "Zone catalog"). scale multiplies the profile shape.
# --------------------------------------------------------------------------- #

ZONE_CATALOG = [
    # zone_id, facility_id, name, capacity, visitor_allowed, note, profile, rule set, curve scale
    ("bpa-main-st", "fac-main-st-meters", "Main St RapidPark", 40, True, BPA_STREET_NOTE,
     "core_long", "rapidpark", 1.0),
    ("bpa-e3rd-west", "fac-e3rd-st-meters", "E 3rd St RapidPark West", 45, True, BPA_STREET_NOTE,
     "core_long", "rapidpark", 1.0),
    ("bpa-e3rd-east", "fac-e3rd-st-meters", "E 3rd St RapidPark East", 45, True, BPA_STREET_NOTE,
     "core_long", "rapidpark", 0.99),
    ("bpa-e4th", "fac-e4th-st-meters", "E 4th St RapidPark", 35, True, BPA_STREET_NOTE,
     "short_stay", "rapidpark", 1.0),
    ("bpa-new-st", "fac-new-st-meters", "New St FlexPark", 30, True, BPA_STREET_NOTE,
     "short_stay", "flexpark", 0.9),
    ("bpa-morton", "fac-morton-ave-meters", "Morton Ave FlexPark", 30, True, BPA_STREET_NOTE,
     "quiet", "flexpark", 1.0),
    ("bpa-polk-garage", "fac-polk-st-garage", "Polk Street Garage", 731, True, None,
     "garage_commuter", "bpa_garage", 1.0),
    ("bpa-new-st-garage", "fac-new-st-garage", "New Street Garage", 400, True,
     "Entrance at 324 South New Street.", "garage_commuter", "bpa_garage", 0.92),
    ("lps-zoellner-l1", "fac-zoellner-garage", "Zoellner Garage Level 1", 60, True,
     "Visitors park on Level 1 only.", "visitor_garage", "zoellner_visitor", 1.0),
    ("lps-zoellner-l2", "fac-zoellner-garage", "Zoellner Garage Level 2", 120, False, PERMIT_NOTE,
     "permit", "zoellner_permit", 1.0),
    ("lps-zoellner-l3", "fac-zoellner-garage", "Zoellner Garage Level 3", 120, False, PERMIT_NOTE,
     "permit", "zoellner_permit", 0.93),
    ("lps-zoellner-l4", "fac-zoellner-garage", "Zoellner Garage Level 4", 120, False, PERMIT_NOTE,
     "permit", "zoellner_permit", 0.82),
    ("lps-farrington", "fac-farrington-garage", "Farrington Square Lower Level", 52, True,
     "Text2Park available after 4 PM (16:00) and on weekends.", "visitor_garage", "farrington", 0.95),
    ("lps-packer-ave", "fac-packer-ave-meters", "Packer Ave Meters", 25, True, PASSPORT_NOTE,
     "campus_meter", "campus_meter", 1.0),
    ("lps-alumni-l1", "fac-alumni-garage", "Alumni Garage Level 1 Meters", 30, True, PASSPORT_NOTE,
     "campus_meter", "campus_meter", 0.92),
]

# --------------------------------------------------------------------------- #
# Profiles (design "Profile" table) and their hourly shapes
#
# Calibration notes:
# - core_long plateaus at 0.96 so the realized 10:00-18:00 mean clears 0.85
#   (Req 3.9) despite the forced 08:00 ramp from 0.40.
# - quiet uses a 30 min paid mean (design table: 45) and a 0.35 peak. With 45
#   min, Morton's turnover falls below the core_long zones, and because three
#   of the six BPA on-street zones are core_long, Req 3.10 needs every other
#   on-street zone to turn over faster than all three of them.
# --------------------------------------------------------------------------- #

PROFILES = {
    "core_long": {"description": "Downtown core meters: chronic shortage and long stays near the limit.",
                  "curve_peak": 0.96, "curve_window": "Mon-Sat 10:00-18:00, about 0.5 by 20:00",
                  "dwell_frac": 0.95, "mean_stay_min": 110},
    "short_stay": {"description": "High-turnover on-street comparators.",
                   "curve_peak": 0.65, "curve_window": "Mon-Sat midday and early evening",
                   "dwell_frac": None, "mean_stay_min": 45},
    "quiet": {"description": "Low-demand meters with short stays.",
              "curve_peak": 0.35, "curve_window": "Mon-Sat 09:00-18:00",
              "dwell_frac": None, "mean_stay_min": 30},
    "garage_commuter": {"description": "BPA garages with weekday commuters.",
                        "curve_peak": 0.6, "curve_window": "Mon-Fri 09:00-17:00",
                        "dwell_frac": None, "mean_stay_min": 240},
    "visitor_garage": {"description": "Campus visitor garages with evening and weekend bumps.",
                       "curve_peak": 0.7, "curve_window": "daily 10:00-17:00 at 0.55, Fri-Sat evenings higher",
                       "dwell_frac": None, "mean_stay_min": 120},
    "campus_meter": {"description": "Campus meters during class hours.",
                     "curve_peak": 0.8, "curve_window": "Mon-Fri 09:00-16:00",
                     "dwell_frac": 0.6, "mean_stay_min": 72},
    "permit": {"description": "Permit-only garage levels, invisible to visitors.",
               "curve_peak": 0.75, "curve_window": "Mon-Fri 08:00-16:00",
               "dwell_frac": None, "mean_stay_min": 300},
}

# Hourly shapes in thousandths: (first_hour, end_hour_exclusive, value) spans per day type.
# Day types: mon_thu, fri, sat, sun. Only enforced hours are used; shaping then
# applies the first-hour cap and the step limit, so ramps are produced automatically.
_CORE = [(0, 18, 960), (18, 24, 500)]
_SHORT_WEEKDAY = [(0, 9, 300), (9, 10, 400), (10, 11, 500), (11, 12, 600), (12, 14, 650),
                  (14, 15, 550), (15, 17, 500), (17, 18, 550), (18, 19, 600), (19, 20, 550), (20, 24, 450)]
_SHORT_FRI_SAT = [(0, 9, 300), (9, 10, 420), (10, 11, 530), (11, 12, 620), (12, 14, 670),
                  (14, 15, 580), (15, 17, 540), (17, 18, 600), (18, 20, 650), (20, 24, 550)]
_QUIET = [(0, 9, 300), (9, 18, 350), (18, 24, 300)]
_QUIET_SAT = [(0, 9, 280), (9, 18, 330), (18, 24, 280)]
_GARAGE_WEEKDAY = [(0, 7, 200), (7, 8, 350), (8, 9, 500), (9, 17, 600), (17, 18, 500), (18, 19, 400),
                   (19, 20, 350), (20, 21, 320), (21, 22, 280), (22, 23, 200), (23, 24, 120)]
_GARAGE_SAT = [(0, 7, 80), (7, 8, 120), (8, 9, 180), (9, 10, 250), (10, 11, 320), (11, 17, 380),
               (17, 18, 360), (18, 19, 400), (19, 21, 420), (21, 22, 380), (22, 23, 300), (23, 24, 200)]
_GARAGE_SUN = [(0, 7, 50), (7, 8, 80), (8, 9, 120), (9, 10, 180), (10, 17, 240), (17, 18, 220),
               (18, 19, 200), (19, 20, 180), (20, 21, 150), (21, 22, 120), (22, 23, 100), (23, 24, 80)]
_VISITOR_WEEKDAY = [(0, 7, 150), (7, 8, 250), (8, 9, 350), (9, 10, 450), (10, 17, 550), (17, 18, 500),
                    (18, 19, 550), (19, 21, 620), (21, 22, 520), (22, 23, 400), (23, 24, 250)]
_VISITOR_FRI = [(0, 7, 150), (7, 8, 250), (8, 9, 350), (9, 10, 450), (10, 17, 550), (17, 18, 550),
                (18, 19, 630), (19, 21, 700), (21, 22, 600), (22, 23, 450), (23, 24, 300)]
_VISITOR_SAT = [(0, 7, 100), (7, 8, 150), (8, 9, 250), (9, 10, 400), (10, 17, 600), (17, 18, 580),
                (18, 19, 620), (19, 21, 700), (21, 22, 600), (22, 23, 450), (23, 24, 300)]
_VISITOR_SUN = [(0, 7, 100), (7, 8, 150), (8, 9, 220), (9, 10, 350), (10, 17, 550), (17, 18, 500),
                (18, 19, 420), (19, 20, 380), (20, 21, 350), (21, 22, 300), (22, 23, 220), (23, 24, 150)]
_CAMPUS_WEEKDAY = [(0, 8, 350), (8, 9, 600), (9, 16, 800), (16, 24, 650)]
_CAMPUS_FRI = [(0, 8, 350), (8, 9, 580), (9, 12, 760), (12, 16, 700), (16, 24, 550)]
_PERMIT_WEEKDAY = [(0, 8, 400), (8, 16, 750), (16, 24, 650)]
_PERMIT_FRI = [(0, 8, 400), (8, 12, 700), (12, 16, 650), (16, 24, 550)]

PROFILE_SHAPES = {
    "core_long": {"mon_thu": _CORE, "fri": _CORE, "sat": _CORE, "sun": _CORE},
    "short_stay": {"mon_thu": _SHORT_WEEKDAY, "fri": _SHORT_FRI_SAT, "sat": _SHORT_FRI_SAT,
                   "sun": _SHORT_WEEKDAY},
    "quiet": {"mon_thu": _QUIET, "fri": _QUIET, "sat": _QUIET_SAT, "sun": _QUIET_SAT},
    "garage_commuter": {"mon_thu": _GARAGE_WEEKDAY, "fri": _GARAGE_WEEKDAY, "sat": _GARAGE_SAT,
                        "sun": _GARAGE_SUN},
    "visitor_garage": {"mon_thu": _VISITOR_WEEKDAY, "fri": _VISITOR_FRI, "sat": _VISITOR_SAT,
                       "sun": _VISITOR_SUN},
    "campus_meter": {"mon_thu": _CAMPUS_WEEKDAY, "fri": _CAMPUS_FRI, "sat": _CAMPUS_WEEKDAY,
                     "sun": _CAMPUS_WEEKDAY},
    "permit": {"mon_thu": _PERMIT_WEEKDAY, "fri": _PERMIT_FRI, "sat": _PERMIT_WEEKDAY,
               "sun": _PERMIT_WEEKDAY},
}

# --------------------------------------------------------------------------- #
# Destinations, event templates, scenarios
# --------------------------------------------------------------------------- #

DESTINATIONS = [
    {"destination_id": "zoellner", "name": "Zoellner Arts Center", "lat": 40.608, "lng": -75.3726},
    {"destination_id": "goodman", "name": "Goodman Stadium", "lat": 40.5889, "lng": -75.3553},
    {"destination_id": "alumni-memorial", "name": "Alumni Memorial Building", "lat": 40.607, "lng": -75.3797},
    {"destination_id": "third-street", "name": "3rd Street shops", "lat": 40.6128, "lng": -75.3778},
]

# Schedule rules, expanded by api/app/events.py relative to the API start date:
# - alternate_saturdays: day_of_week 5, every interval_days from the anchor (the
#   first Saturday on or after today), forward and backward.
# - weekly: every listed day_of_week.
# - single_weekend: one event starting on the Saturday at anchor + anchor_offset_days,
#   ending end_day_offset days later at "end".
EVENT_TEMPLATES = [
    {"template_id": "football", "name": "Lehigh Football Home Game", "destination_id": "goodman",
     "rule": {"kind": "alternate_saturdays", "day_of_week": 5, "interval_days": 14,
              "start": "12:00", "end": "16:00"},
     "expected_attendance": 12000,
     "impacts": {"lps-packer-ave": 1.6, "lps-farrington": 1.4, "lps-zoellner-l1": 1.3,
                 "bpa-polk-garage": 1.3, "bpa-new-st-garage": 1.25, "bpa-e3rd-west": 1.2}},
    {"template_id": "zoellner_performance", "name": "Zoellner Evening Performance",
     "destination_id": "zoellner",
     "rule": {"kind": "weekly", "days_of_week": [4, 5], "start": "19:30", "end": "22:00"},
     "expected_attendance": 900,
     "impacts": {"lps-zoellner-l1": 1.5, "lps-farrington": 1.2, "bpa-e4th": 1.15}},
    {"template_id": "family_weekend", "name": "Lehigh Family Weekend", "destination_id": "alumni-memorial",
     "rule": {"kind": "single_weekend", "day_of_week": 5, "anchor_offset_days": 7,
              "start": "09:00", "end_day_offset": 1, "end": "17:00"},
     "expected_attendance": 6000,
     "impacts": {"lps-zoellner-l1": 1.5, "lps-farrington": 1.5, "lps-alumni-l1": 1.5,
                 "lps-packer-ave": 1.4, "bpa-new-st-garage": 1.3, "bpa-polk-garage": 1.2,
                 "bpa-e4th": 1.2, "bpa-new-st": 1.2, "bpa-e3rd-west": 1.15, "bpa-e3rd-east": 1.15}},
]

SCENARIOS = {
    "game_day": {"template_id": "football", "event_name": "Game Day (Live Demo)", "duration_min": 45},
    "family_weekend": {"template_id": "family_weekend", "event_name": "Family Weekend (Live Demo)",
                       "duration_min": 45},
}

# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _day_type(day: int) -> str:
    return "mon_thu" if day <= 3 else DAY_ABBR[day]


def _shape_value(spans: list[tuple[int, int, int]], hour: int) -> int:
    for first, end, value in spans:
        if first <= hour < end:
            return value
    raise ValueError(f"no shape span covers hour {hour}")


def build_zones() -> list[dict]:
    return [
        {"zone_id": zid, "facility_id": fid, "name": name, "capacity": cap,
         "visitor_allowed": visitor, "note": note, "profile": profile}
        for zid, fid, name, cap, visitor, note, profile, _rules, _scale in ZONE_CATALOG
    ]


def build_rate_rules() -> list[dict]:
    rules = []
    for zid, *_rest, rule_set, _scale in ZONE_CATALOG:
        spec = RULE_SETS[rule_set]
        for day in spec["days"]:
            rules.append({
                "rule_id": f"{zid}-{DAY_ABBR[day]}", "zone_id": zid, "day_of_week": day,
                "start": spec["start"], "end": spec["end"], "hourly_rate": spec["hourly_rate"],
                "time_limit_min": spec["time_limit_min"], "placeholder": spec["placeholder"],
                "source": spec["source"],
            })
    return rules


def enforced_hours(rule_set: str) -> list[bool]:
    """168 flags: True when a rate rule covers the whole hour-of-week slot."""
    spec = RULE_SETS[rule_set]
    start, end = _minutes(spec["start"]), _minutes(spec["end"])
    if start % 60 or end % 60:
        raise ValueError(f"rule set {rule_set} must start and end on the hour")
    flags = [False] * 168
    for day in spec["days"]:
        for hour in range(start // 60, end // 60):
            flags[day * 24 + hour] = True
    return flags


def build_curve(profile: str, rule_set: str, scale: float) -> list[float]:
    enforced = enforced_hours(rule_set)
    shapes = PROFILE_SHAPES[profile]
    raw = [min(TARGET_MAX, round(_shape_value(shapes[_day_type(how // 24)], how % 24) * scale))
           for how in range(168)]
    run_starts = [how for how in range(168) if enforced[how] and not enforced[how - 1]]
    if not run_starts:
        raise ValueError(f"rule set {rule_set} has no unenforced hour")

    values = [0] * 168  # thousandths
    for first in run_starts:
        prev = None
        how = first
        while enforced[how % 168]:
            idx = how % 168
            if prev is None:
                value = min(raw[idx], FIRST_HOUR_MAX)
            else:
                value = max(prev - MAX_STEP, min(prev + MAX_STEP, raw[idx]))
            values[idx] = value
            prev = value
            how += 1

    curve = []
    for how in range(168):
        if enforced[how]:
            curve.append(values[how] / 1000)
        elif enforced[how - 1]:  # first hour after enforcement (cyclic over the week)
            curve.append(values[how - 1] / POST_ENFORCEMENT_DIVISOR)
        else:
            curve.append(0.0)
    return curve


def build_seed() -> dict:
    return {
        "operators": OPERATORS,
        "facilities": FACILITIES,
        "zones": build_zones(),
        "rate_rules": build_rate_rules(),
        "destinations": DESTINATIONS,
        "event_templates": EVENT_TEMPLATES,
        "demand_curves": {zid: build_curve(profile, rule_set, scale)
                          for zid, _f, _n, _c, _v, _note, profile, rule_set, scale in ZONE_CATALOG},
        "profiles": PROFILES,
        "scenarios": SCENARIOS,
    }

# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def validate(seed: dict) -> list[str]:
    errors: list[str] = []

    def unique(rows: list[dict], key: str, table: str) -> set:
        ids = [row[key] for row in rows]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            errors.append(f"{table}: duplicate {key} {dupes}")
        return set(ids)

    operator_ids = unique(seed["operators"], "operator_id", "operators")
    facility_ids = unique(seed["facilities"], "facility_id", "facilities")
    zone_ids = unique(seed["zones"], "zone_id", "zones")
    unique(seed["rate_rules"], "rule_id", "rate_rules")
    destination_ids = unique(seed["destinations"], "destination_id", "destinations")
    template_ids = unique(seed["event_templates"], "template_id", "event_templates")

    if len(zone_ids) != 15:
        errors.append(f"zones: expected 15, found {len(zone_ids)}")
    for fac in seed["facilities"]:
        if fac["operator_id"] not in operator_ids:
            errors.append(f"facility {fac['facility_id']}: unknown operator {fac['operator_id']}")
        if fac["type"] not in ("garage", "lot", "street"):
            errors.append(f"facility {fac['facility_id']}: bad type {fac['type']}")
    for zone in seed["zones"]:
        if zone["facility_id"] not in facility_ids:
            errors.append(f"zone {zone['zone_id']}: unknown facility {zone['facility_id']}")
        if not (isinstance(zone["capacity"], int) and zone["capacity"] > 0):
            errors.append(f"zone {zone['zone_id']}: capacity must be a positive integer")
        if zone["profile"] not in seed["profiles"]:
            errors.append(f"zone {zone['zone_id']}: unknown profile {zone['profile']}")
    for rule in seed["rate_rules"]:
        if rule["zone_id"] not in zone_ids:
            errors.append(f"rule {rule['rule_id']}: unknown zone {rule['zone_id']}")
        if not 0 <= rule["day_of_week"] <= 6:
            errors.append(f"rule {rule['rule_id']}: day_of_week out of range")
        if not 0 <= _minutes(rule["start"]) < _minutes(rule["end"]) <= 1440:
            errors.append(f"rule {rule['rule_id']}: start must precede end within the day")
        if not rule["placeholder"] and not rule["source"]:
            errors.append(f"rule {rule['rule_id']}: placeholder false requires a source")
        limit = rule["time_limit_min"]
        if limit is not None and (limit <= 0 or limit % 15):
            errors.append(f"rule {rule['rule_id']}: time limit must be a positive multiple of 15")
    for tpl in seed["event_templates"]:
        if tpl["destination_id"] not in destination_ids:
            errors.append(f"template {tpl['template_id']}: unknown destination {tpl['destination_id']}")
        for zid, boost in tpl["impacts"].items():
            if zid not in zone_ids:
                errors.append(f"template {tpl['template_id']}: unknown zone {zid}")
            if boost < 1.0:
                errors.append(f"template {tpl['template_id']}: boost for {zid} below 1.0")
    for name, scenario in seed["scenarios"].items():
        if scenario["template_id"] not in template_ids:
            errors.append(f"scenario {name}: unknown template {scenario['template_id']}")

    curves = seed["demand_curves"]
    if set(curves) != zone_ids:
        errors.append("demand_curves: keys must match zone IDs exactly")
    rule_set_by_zone = {zid: rule_set for zid, *_rest, rule_set, _scale in ZONE_CATALOG}
    for zid, curve in curves.items():
        if len(curve) != 168:
            errors.append(f"curve {zid}: expected 168 values, found {len(curve)}")
            continue
        enforced = enforced_hours(rule_set_by_zone[zid])
        for how in range(168):
            value, prev = curve[how], curve[how - 1]
            if not 0.0 <= value <= TARGET_MAX / 1000:
                errors.append(f"curve {zid}[{how}]: {value} outside [0, 0.98]")
            if enforced[how]:
                if not enforced[how - 1] and value > FIRST_HOUR_MAX / 1000:
                    errors.append(f"curve {zid}[{how}]: first enforced hour above 0.40")
                if enforced[how - 1] and abs(value - prev) > 0.15:
                    errors.append(f"curve {zid}[{how}]: step from previous hour above 0.15")
            elif enforced[how - 1]:
                if abs(value - 0.1 * prev) > 1e-9:
                    errors.append(f"curve {zid}[{how}]: first unenforced hour must be 0.1 x previous")
            elif value != 0.0:
                errors.append(f"curve {zid}[{how}]: unenforced hour must be 0.0")
    return errors

# --------------------------------------------------------------------------- #
# Deterministic JSON writer: one record per line, curves wrapped at 24 values
# --------------------------------------------------------------------------- #


def _is_scalar(value) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def _is_flat(value) -> bool:
    if _is_scalar(value):
        return True
    if isinstance(value, list):
        return len(value) <= 24 and all(_is_scalar(v) for v in value)
    if isinstance(value, dict):
        return all(_is_scalar(v) or (isinstance(v, list) and len(v) <= 24 and all(map(_is_scalar, v)))
                   for v in value.values())
    return False


def _render(value, depth: int = 0) -> str:
    pad, inner = "  " * depth, "  " * (depth + 1)
    if _is_flat(value):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, dict):
        body = ",\n".join(f"{inner}{json.dumps(k)}: {_render(v, depth + 1)}" for k, v in value.items())
        return "{\n" + body + "\n" + pad + "}"
    if all(_is_scalar(v) for v in value):  # long scalar list: 24 values per line
        rows = [", ".join(json.dumps(v) for v in value[i:i + 24]) for i in range(0, len(value), 24)]
        return "[\n" + ",\n".join(inner + row for row in rows) + "\n" + pad + "]"
    body = ",\n".join(inner + _render(v, depth + 1) for v in value)
    return "[\n" + body + "\n" + pad + "]"


def main() -> int:
    seed = build_seed()
    errors = validate(seed)
    if errors:
        for error in errors:
            print(f"seed validation failed: {error}", file=sys.stderr)
        return 1
    text = _render(seed) + "\n"
    if json.loads(text) != seed:
        print("seed validation failed: rendered JSON does not round-trip", file=sys.stderr)
        return 1
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"Wrote {OUT} ({len(seed['zones'])} zones, {len(seed['rate_rules'])} rate rules, "
          f"{len(seed['event_templates'])} event templates)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
