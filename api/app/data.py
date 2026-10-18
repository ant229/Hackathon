"""SpotStack Data_Store: the nine-table schema, seed loading, and shared helpers.

The nine tables (Req 1.1) map 1:1 to the deferred Supabase schema in the
read-only `claude output/Hackathon` scaffold (`Session` -> `parking_session`,
other names lowercase snake case):

    Operator, Facility, Zone, Rate_Rule, Session, Destination, Event, Impacts, Zone_Status

Each table is a dataclass held in a dict keyed by its primary key. Sessions are
the one exception: they live in a list where `sessions[i].session_id == i`,
because the session key is an internal integer. No table has a plate,
vehicle, or person column (Req 16.1).

Every timestamp is timezone-aware, and day-of-week and hour-of-day are always
evaluated in America/New_York local time (Req 1.13). Positions are WGS84
decimal degrees (Req 1.11).

`load_seed()` builds the static tables from fixtures/seed.json. The Event and
Impacts tables start empty; `app.events.expand_events` produces their rows and
callers insert them with `DataStore.add_events()`. `validate()` checks the whole
store, so it also covers events, impacts, and sessions once they exist.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")
SEED_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "seed.json"
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)  # Zone_Status.updated_at before the first update

FACILITY_TYPES = frozenset({"garage", "lot", "street"})
EARTH_RADIUS_M = 6_371_008.8
WALK_DETOUR = 1.3
WALK_SPEED_M_PER_MIN = 80.0
CURVE_LENGTH = 168


class SeedValidationError(ValueError):
    """Raised when the Data_Store breaks a schema rule. The message names the offending key."""


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Operator:
    operator_id: str
    name: str
    pay_app: tuple[str, ...]  # every payment app the Operator accepts (Req 1.2)


@dataclass(frozen=True, slots=True)
class Facility:
    facility_id: str
    operator_id: str  # FK -> Operator
    name: str
    type: str  # garage | lot | street
    lat: float
    lng: float


@dataclass(frozen=True, slots=True)
class Zone:
    zone_id: str
    facility_id: str  # FK -> Facility
    name: str
    capacity: int  # > 0
    visitor_allowed: bool
    note: str | None
    profile: str  # key into DataStore.profiles


@dataclass(frozen=True, slots=True)
class RateRule:
    rule_id: str
    zone_id: str  # FK -> Zone
    day_of_week: int  # 0 = Monday ... 6 = Sunday
    start_min: int  # local minute of day, inclusive (0-1439)
    end_min: int  # local minute of day, exclusive (1-1440; 1440 = "24:00")
    hourly_rate: float
    time_limit_min: int | None  # None = no time limit
    placeholder: bool
    source: str | None


@dataclass(slots=True)
class Session:
    session_id: int  # internal PK; equals the index in DataStore.sessions
    zone_id: str  # FK -> Zone
    start_time: datetime
    paid_until: datetime
    end_time: datetime  # actual departure; a scenario reset may move it to "now"
    event_id: str | None = None  # FK -> Event
    injected: bool = False  # created by a live demo scenario


@dataclass(frozen=True, slots=True)
class Destination:
    destination_id: str
    name: str
    lat: float
    lng: float


@dataclass(slots=True)
class Event:
    event_id: str
    destination_id: str  # FK -> Destination
    name: str
    start_time: datetime
    end_time: datetime  # a scenario reset may move it to "now"
    expected_attendance: int
    # Live demo events use [trigger, expires_at] instead of the Boost_Window.
    window_override: tuple[datetime, datetime] | None = None


@dataclass(frozen=True, slots=True)
class Impact:
    event_id: str  # PK part, FK -> Event
    zone_id: str  # PK part, FK -> Zone
    demand_boost: float  # >= 1.0


@dataclass(slots=True)
class ZoneStatus:
    zone_id: str  # PK and FK -> Zone
    occupied: float = 0.0  # active_sessions / capacity, 0.0-1.0
    active_sessions: int = 0
    opening_soon: int = 0
    updated_at: datetime = EPOCH


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #


@dataclass
class DataStore:
    operators: dict[str, Operator] = field(default_factory=dict)
    facilities: dict[str, Facility] = field(default_factory=dict)
    zones: dict[str, Zone] = field(default_factory=dict)
    rate_rules: dict[str, RateRule] = field(default_factory=dict)
    sessions: list[Session] = field(default_factory=list)
    destinations: dict[str, Destination] = field(default_factory=dict)
    events: dict[str, Event] = field(default_factory=dict)
    impacts: dict[tuple[str, str], Impact] = field(default_factory=dict)  # (event_id, zone_id)
    zone_status: dict[str, ZoneStatus] = field(default_factory=dict)
    # Raw seed sections used by the simulator and events expansion.
    demand_curves: dict[str, list[float]] = field(default_factory=dict)  # zone_id -> 168 targets
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    event_templates: list[dict[str, Any]] = field(default_factory=list)
    scenarios: dict[str, dict[str, Any]] = field(default_factory=dict)
    # zone_id -> 7 tuples (Monday..Sunday) of rules sorted by start_min; see rebuild_rule_index().
    rules_by_zone_day: dict[str, tuple[tuple[RateRule, ...], ...]] = field(default_factory=dict)

    def rebuild_rule_index(self) -> None:
        """Index rate rules by zone and day for applicable_rule(). Call after editing rate_rules."""
        index: dict[str, list[list[RateRule]]] = {zid: [[] for _ in range(7)] for zid in self.zones}
        for rule in self.rate_rules.values():
            index[rule.zone_id][rule.day_of_week].append(rule)
        self.rules_by_zone_day = {
            zid: tuple(tuple(sorted(day, key=lambda r: r.start_min)) for day in days)
            for zid, days in index.items()
        }

    def facility_of(self, zone_id: str) -> Facility:
        return self.facilities[self.zones[zone_id].facility_id]

    def operator_of(self, zone_id: str) -> Operator:
        return self.operators[self.facility_of(zone_id).operator_id]

    def add_events(self, events: Iterable[Event], impacts: Iterable[Impact]) -> None:
        """Insert Event and Impacts rows atomically.

        Raises SeedValidationError, naming the key, on a duplicate Event_ID or
        Impacts PK, a dangling FK, an invalid time range, or a boost below 1.0.
        Nothing is inserted when any row fails.
        """
        new_events: dict[str, Event] = {}
        for event in events:
            if event.event_id in self.events or event.event_id in new_events:
                raise SeedValidationError(f"Event: duplicate event_id {event.event_id!r}")
            _check_event(self, event)
            new_events[event.event_id] = event
        new_impacts: dict[tuple[str, str], Impact] = {}
        for impact in impacts:
            key = (impact.event_id, impact.zone_id)
            if key in self.impacts or key in new_impacts:
                raise SeedValidationError(f"Impacts: duplicate primary key {key!r}")
            if impact.event_id not in self.events and impact.event_id not in new_events:
                raise SeedValidationError(f"Impacts {key!r}: unknown event_id {impact.event_id!r}")
            _check_impact(self, impact)
            new_impacts[key] = impact
        self.events.update(new_events)
        self.impacts.update(new_impacts)

    def validate(self) -> None:
        """Check every table and relationship (Req 1.12). Fails fast with the offending key."""
        _validate(self)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _require_aware(ts: datetime, what: str = "timestamp") -> None:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"{what} must be timezone-aware, got naive {ts.isoformat()}")


def hour_of_week(ts: datetime) -> int:
    """Hour_Of_Week 0-167 in America/New_York local time: weekday (Monday = 0) * 24 + hour."""
    _require_aware(ts)
    local = ts.astimezone(TZ)
    return local.weekday() * 24 + local.hour


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle (Straight_Line_Distance) meters between two WGS84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def walk_minutes(distance_m: float) -> int:
    """Walk_Minutes: distance x 1.3 detour / 80 m per minute, rounded up (Req 9.4)."""
    return math.ceil(distance_m * WALK_DETOUR / WALK_SPEED_M_PER_MIN)


def applicable_rule(store: DataStore, zone_id: str, ts: datetime) -> RateRule | None:
    """The Rate_Rule in force at ts: local day matches and start_min <= local minute < end_min.

    Returns None outside Enforcement_Hours. Raises KeyError for an unknown zone and
    ValueError for a naive ts.
    """
    _require_aware(ts)
    local = ts.astimezone(TZ)
    minute = local.hour * 60 + local.minute
    for rule in store.rules_by_zone_day[zone_id][local.weekday()]:
        if rule.start_min <= minute < rule.end_min:
            return rule
    return None


def is_time_limited(store: DataStore, zone_id: str, ts: datetime) -> bool:
    """True when the zone is a Time_Limited_Zone at ts (applicable rule has a time limit)."""
    rule = applicable_rule(store, zone_id, ts)
    return rule is not None and rule.time_limit_min is not None


def parse_hhmm(value: str) -> int:
    """Parse a local "HH:MM" string (with "24:00" = end of day) into minutes 0-1440."""
    parts = value.split(":") if isinstance(value, str) else []
    if len(parts) != 2 or not all(len(p) == 2 and p.isdigit() for p in parts):
        raise ValueError(f"expected 'HH:MM', got {value!r}")
    hours, minutes = int(parts[0]), int(parts[1])
    if minutes >= 60 or hours > 24 or (hours == 24 and minutes):
        raise ValueError(f"time out of range: {value!r}")
    return hours * 60 + minutes


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def _keyed(rows: Iterable[Any], key: str, table: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in rows:
        pk = getattr(row, key)
        if pk in out:
            raise SeedValidationError(f"{table}: duplicate {key} {pk!r}")
        out[pk] = row
    return out


def load_seed(path: str | Path = SEED_PATH) -> DataStore:
    """Load and validate the seed fixture. Events and Impacts start empty."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        store = DataStore(
            operators=_keyed(
                (Operator(o["operator_id"], o["name"], tuple(o["pay_app"])) for o in raw["operators"]),
                "operator_id", "Operator"),
            facilities=_keyed(
                (Facility(f["facility_id"], f["operator_id"], f["name"], f["type"],
                          float(f["lat"]), float(f["lng"])) for f in raw["facilities"]),
                "facility_id", "Facility"),
            zones=_keyed(
                (Zone(z["zone_id"], z["facility_id"], z["name"], z["capacity"],
                      z["visitor_allowed"], z.get("note"), z["profile"]) for z in raw["zones"]),
                "zone_id", "Zone"),
            rate_rules=_keyed(
                (RateRule(r["rule_id"], r["zone_id"], r["day_of_week"], parse_hhmm(r["start"]),
                          parse_hhmm(r["end"]), float(r["hourly_rate"]), r["time_limit_min"],
                          bool(r["placeholder"]), r.get("source")) for r in raw["rate_rules"]),
                "rule_id", "Rate_Rule"),
            destinations=_keyed(
                (Destination(d["destination_id"], d["name"], float(d["lat"]), float(d["lng"]))
                 for d in raw["destinations"]),
                "destination_id", "Destination"),
            demand_curves={zid: [float(v) for v in curve] for zid, curve in raw["demand_curves"].items()},
            profiles=raw["profiles"],
            event_templates=raw["event_templates"],
            scenarios=raw["scenarios"],
        )
    except KeyError as exc:
        raise SeedValidationError(f"seed is missing required key {exc.args[0]!r}") from exc
    except ValueError as exc:
        if isinstance(exc, SeedValidationError):
            raise
        raise SeedValidationError(f"seed has an invalid value: {exc}") from exc
    store.zone_status = {zid: ZoneStatus(zid) for zid in store.zones}
    store.validate()
    store.rebuild_rule_index()
    return store


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def _fail(message: str) -> None:
    raise SeedValidationError(message)


def _check_event(store: DataStore, event: Event) -> None:
    eid = event.event_id
    if event.destination_id not in store.destinations:
        _fail(f"Event {eid!r}: unknown destination_id {event.destination_id!r}")
    for ts, what in ((event.start_time, "start_time"), (event.end_time, "end_time")):
        if ts.tzinfo is None or ts.utcoffset() is None:
            _fail(f"Event {eid!r}: {what} must be timezone-aware")
    if event.end_time < event.start_time:
        _fail(f"Event {eid!r}: end_time precedes start_time")
    if event.window_override is not None:
        lo, hi = event.window_override
        if lo.tzinfo is None or hi.tzinfo is None or hi < lo:
            _fail(f"Event {eid!r}: window_override must be an aware, ordered pair")


def _check_impact(store: DataStore, impact: Impact) -> None:
    key = (impact.event_id, impact.zone_id)
    if impact.zone_id not in store.zones:
        _fail(f"Impacts {key!r}: unknown zone_id {impact.zone_id!r}")
    if not impact.demand_boost >= 1.0:
        _fail(f"Impacts {key!r}: demand_boost {impact.demand_boost} is below 1.0")


def _validate(store: DataStore) -> None:
    for oid, op in store.operators.items():
        if op.operator_id != oid:
            _fail(f"Operator {oid!r}: key does not match operator_id {op.operator_id!r}")

    for fid, fac in store.facilities.items():
        if fac.facility_id != fid:
            _fail(f"Facility {fid!r}: key does not match facility_id {fac.facility_id!r}")
        if fac.operator_id not in store.operators:
            _fail(f"Facility {fid!r}: unknown operator_id {fac.operator_id!r}")
        if fac.type not in FACILITY_TYPES:
            _fail(f"Facility {fid!r}: type {fac.type!r} is not garage, lot, or street")
        if not (-90 <= fac.lat <= 90 and -180 <= fac.lng <= 180):
            _fail(f"Facility {fid!r}: lat/lng outside WGS84 range")

    for zid, zone in store.zones.items():
        if zone.zone_id != zid:
            _fail(f"Zone {zid!r}: key does not match zone_id {zone.zone_id!r}")
        if zone.facility_id not in store.facilities:
            _fail(f"Zone {zid!r}: unknown facility_id {zone.facility_id!r}")
        if isinstance(zone.capacity, bool) or not isinstance(zone.capacity, int) or zone.capacity <= 0:
            _fail(f"Zone {zid!r}: capacity must be a positive integer, got {zone.capacity!r}")
        if zone.profile not in store.profiles:
            _fail(f"Zone {zid!r}: unknown profile {zone.profile!r}")

    by_zone_day: dict[tuple[str, int], list[RateRule]] = {}
    for rid, rule in store.rate_rules.items():
        if rule.rule_id != rid:
            _fail(f"Rate_Rule {rid!r}: key does not match rule_id {rule.rule_id!r}")
        if rule.zone_id not in store.zones:
            _fail(f"Rate_Rule {rid!r}: unknown zone_id {rule.zone_id!r}")
        if not 0 <= rule.day_of_week <= 6:
            _fail(f"Rate_Rule {rid!r}: day_of_week {rule.day_of_week} outside 0-6")
        if not 0 <= rule.start_min < rule.end_min <= 1440:
            _fail(f"Rate_Rule {rid!r}: start must precede end within the day")
        if rule.hourly_rate < 0:
            _fail(f"Rate_Rule {rid!r}: hourly_rate is negative")
        if rule.time_limit_min is not None and rule.time_limit_min <= 0:
            _fail(f"Rate_Rule {rid!r}: time_limit_min must be positive or null")
        by_zone_day.setdefault((rule.zone_id, rule.day_of_week), []).append(rule)
    for (zid, day), rules in by_zone_day.items():
        rules.sort(key=lambda r: r.start_min)
        for prev, cur in zip(rules, rules[1:]):
            if cur.start_min < prev.end_min:
                _fail(f"Rate_Rule {cur.rule_id!r}: overlaps {prev.rule_id!r} on zone {zid!r} day {day}")

    for did, dest in store.destinations.items():
        if dest.destination_id != did:
            _fail(f"Destination {did!r}: key does not match destination_id {dest.destination_id!r}")
        if not (-90 <= dest.lat <= 90 and -180 <= dest.lng <= 180):
            _fail(f"Destination {did!r}: lat/lng outside WGS84 range")

    for eid, event in store.events.items():
        if event.event_id != eid:
            _fail(f"Event {eid!r}: key does not match event_id {event.event_id!r}")
        _check_event(store, event)

    for key, impact in store.impacts.items():
        if (impact.event_id, impact.zone_id) != key:
            _fail(f"Impacts {key!r}: key does not match row ({impact.event_id!r}, {impact.zone_id!r})")
        if impact.event_id not in store.events:
            _fail(f"Impacts {key!r}: unknown event_id {impact.event_id!r}")
        _check_impact(store, impact)

    for zid in store.zones:
        if zid not in store.zone_status:
            _fail(f"Zone_Status: missing row for zone_id {zid!r}")
    for zid, status in store.zone_status.items():
        if status.zone_id != zid:
            _fail(f"Zone_Status {zid!r}: duplicate or mismatched row for zone_id {status.zone_id!r}")
        if zid not in store.zones:
            _fail(f"Zone_Status {zid!r}: unknown zone_id")
        if not 0.0 <= status.occupied <= 1.0:
            _fail(f"Zone_Status {zid!r}: occupied {status.occupied} outside 0.0-1.0")
        if status.active_sessions < 0 or status.opening_soon < 0:
            _fail(f"Zone_Status {zid!r}: counts must be non-negative")
        if status.updated_at.tzinfo is None:
            _fail(f"Zone_Status {zid!r}: updated_at must be timezone-aware")

    for i, session in enumerate(store.sessions):
        sid = session.session_id
        if sid != i:
            _fail(f"Session {sid!r}: session_id does not match its position {i}")
        if session.zone_id not in store.zones:
            _fail(f"Session {sid}: unknown zone_id {session.zone_id!r}")
        if session.event_id is not None and session.event_id not in store.events:
            _fail(f"Session {sid}: unknown event_id {session.event_id!r}")
        if session.start_time.tzinfo is None or session.paid_until.tzinfo is None \
                or session.end_time.tzinfo is None:
            _fail(f"Session {sid}: timestamps must be timezone-aware")

    for zid, curve in store.demand_curves.items():
        if zid not in store.zones:
            _fail(f"demand_curves: unknown zone_id {zid!r}")
        if len(curve) != CURVE_LENGTH:
            _fail(f"demand_curves {zid!r}: expected {CURVE_LENGTH} values, found {len(curve)}")
    for zid in store.zones:
        if zid not in store.demand_curves:
            _fail(f"demand_curves: missing curve for zone_id {zid!r}")

    template_ids: set[str] = set()
    for tpl in store.event_templates:
        tid = tpl.get("template_id")
        if tid in template_ids:
            _fail(f"event_templates: duplicate template_id {tid!r}")
        template_ids.add(tid)
        if tpl.get("destination_id") not in store.destinations:
            _fail(f"event_templates {tid!r}: unknown destination_id {tpl.get('destination_id')!r}")
        for zid, boost in tpl.get("impacts", {}).items():
            if zid not in store.zones:
                _fail(f"event_templates {tid!r}: unknown zone_id {zid!r}")
            if not boost >= 1.0:
                _fail(f"event_templates {tid!r}: demand_boost {boost} for {zid!r} is below 1.0")
    for name, scenario in store.scenarios.items():
        if scenario.get("template_id") not in template_ids:
            _fail(f"scenarios {name!r}: unknown template_id {scenario.get('template_id')!r}")
