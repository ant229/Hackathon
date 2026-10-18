"""Qlik-style associative engine over Sessions (Req 10-12).

Each Field keeps a Symbol_Table (distinct values, insertion order, so indexes
stay stable) and one integer Row_Index column. A Selection becomes one boolean
mask per selected Field; the AND of those masks is the associated row set.
Every Field_Value then gets one of the five Value_States (see ``_state``).

Rows come only from a ``SessionSource`` (Req 18.1). ``sync()`` appends new
sessions and rewrites changed ones, so the model stays current while the
simulator runs. Only counts, sums, averages, values, and states leave this
module: never a row (Req 16.2, 16.3).
"""
from __future__ import annotations

import threading
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import numpy as np

from .data import TZ, DataStore, applicable_rule
from .sources import SessionRecord, SessionSource

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
STAY_BUCKETS = ["Under 30 Min", "30–59 Min", "1–2 H", "2–3 H", "3 H or More"]
OUTCOMES = ["Left Early", "On Time", "Overstayed"]
TIME_OF_WEEK = ["Weekday Class Hours", "Weekday Evening", "Weekend", "Overnight"]
NO_EVENT = "No Event"
NO_LIMIT = "No Limit"
OUTCOME_GRACE = timedelta(minutes=5)

# Display order (Req 10.4).
FIELDS = ["Zone", "Facility Type", "Operator", "Pay App", "Visitor Access", "Day", "Arrival Hour",
          "Time of Week", "Event", "Stay Length", "Outcome", "Time Limit"]

_INITIAL_CAPACITY = 1024


class UnknownField(ValueError):
    def __init__(self, field: str) -> None:
        super().__init__(f"Unknown field '{field}'. Use a field name from /explore/model.")
        self.field = field


class UnknownValue(ValueError):
    def __init__(self, field: str, value: str) -> None:
        super().__init__(f"Field '{field}' has no value '{value}'. Use a value from /explore/model.")
        self.field, self.value = field, value


def stay_bucket(minutes: float) -> str:
    if minutes < 30:
        return STAY_BUCKETS[0]
    if minutes < 60:
        return STAY_BUCKETS[1]
    if minutes < 120:
        return STAY_BUCKETS[2]
    if minutes < 180:
        return STAY_BUCKETS[3]
    return STAY_BUCKETS[4]


def outcome(rec: SessionRecord) -> str:
    if rec.end_time < rec.paid_until - OUTCOME_GRACE:
        return "Left Early"
    if rec.end_time > rec.paid_until + OUTCOME_GRACE:
        return "Overstayed"
    return "On Time"


def time_of_week(weekday: int, hour: int) -> str:
    if 7 <= hour <= 22:
        if weekday >= 5:
            return "Weekend"
        return "Weekday Class Hours" if hour <= 16 else "Weekday Evening"
    return "Overnight"


def _state(selected: bool, field_has_sel: bool, ctx_count: int, assoc_count: int) -> str:
    if selected:
        return "selected" if ctx_count > 0 else "selected_excluded"
    if assoc_count > 0:
        return "possible"
    if field_has_sel and ctx_count > 0:
        return "alternative"
    return "excluded"


class AssociativeEngine:
    def __init__(self, store: DataStore, history_days: int) -> None:
        self.store = store
        self.history_days = history_days
        self.lock = threading.RLock()
        self.symbols: dict[str, list[str]] = {f: [] for f in FIELDS}
        self.pos: dict[str, dict[str, int]] = {f: {} for f in FIELDS}
        # Fixed domains are listed up front so every value has a state even with no rows.
        for f, values in [("Zone", [z.name for z in store.zones.values()]),
                          ("Facility Type", ["Garage", "Lot", "Street"]),
                          ("Visitor Access", ["Visitors Allowed", "Permit Only"]),
                          ("Day", DAYS), ("Arrival Hour", [str(h) for h in range(24)]),
                          ("Time of Week", TIME_OF_WEEK), ("Stay Length", STAY_BUCKETS),
                          ("Outcome", OUTCOMES)]:
            for v in values:
                self._code(f, v)
        self.n = 0
        self._cap = _INITIAL_CAPACITY
        self.cols = {f: np.zeros(self._cap, np.int32) for f in FIELDS}
        self.stay_min = np.zeros(self._cap, np.float32)
        self.revenue = np.zeros(self._cap, np.float32)
        self.slot = np.zeros(self._cap, np.uint8)  # day * 24 + hour
        self.zone_cap = np.array([z.capacity for z in store.zones.values()], np.float64)  # by Zone code
        self.key_to_row: dict[int, int] = {}
        self._source: SessionSource | None = None
        self._cursor = 0
        self._change_cursor = 0

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #

    def _code(self, field: str, value: str) -> int:
        idx = self.pos[field].get(value)
        if idx is None:
            idx = len(self.symbols[field])
            self.symbols[field].append(value)
            self.pos[field][value] = idx
        return idx

    def _grow(self, need: int) -> None:
        if need <= self._cap:
            return
        cap = self._cap
        while cap < need:
            cap *= 2
        for f in FIELDS:
            self.cols[f] = np.resize(self.cols[f], cap)
        self.stay_min = np.resize(self.stay_min, cap)
        self.revenue = np.resize(self.revenue, cap)
        self.slot = np.resize(self.slot, cap)
        self._cap = cap

    def _write(self, row: int, rec: SessionRecord) -> None:
        store = self.store
        zone = store.zones[rec.zone_id]
        facility = store.facilities[zone.facility_id]
        operator = store.operators[facility.operator_id]
        local = rec.start_time.astimezone(TZ)
        rule = applicable_rule(store, rec.zone_id, rec.start_time)
        event = store.events.get(rec.event_id) if rec.event_id else None
        stay = (rec.end_time - rec.start_time).total_seconds() / 60
        paid_h = (rec.paid_until - rec.start_time).total_seconds() / 3600
        values = {
            "Zone": zone.name,
            "Facility Type": facility.type.title(),
            "Operator": operator.name,
            "Pay App": " / ".join(operator.pay_app),
            "Visitor Access": "Visitors Allowed" if zone.visitor_allowed else "Permit Only",
            "Day": DAYS[local.weekday()],
            "Arrival Hour": str(local.hour),
            "Time of Week": time_of_week(local.weekday(), local.hour),
            "Event": event.name if event else NO_EVENT,
            "Stay Length": stay_bucket(stay),
            "Outcome": outcome(rec),
            "Time Limit": f"{rule.time_limit_min / 60:g} H" if rule and rule.time_limit_min else NO_LIMIT,
        }
        for f, v in values.items():
            self.cols[f][row] = self._code(f, v)
        self.stay_min[row] = stay
        self.revenue[row] = (rule.hourly_rate if rule else 0.0) * paid_h
        self.slot[row] = local.weekday() * 24 + local.hour

    def load(self, source: SessionSource) -> None:
        """Attach the source and load every session it has (Req 10.1)."""
        with self.lock:
            self._source = source
            self.sync()

    def sync(self) -> None:
        """Append new sessions and rewrite changed ones (Req 10.12)."""
        if self._source is None:
            return
        with self.lock:
            new, self._cursor = self._source.sessions_since(self._cursor)
            self._grow(self.n + len(new))
            for key, rec in new:
                self.key_to_row[key] = self.n
                self._write(self.n, rec)
                self.n += 1
            changed, self._change_cursor = self._source.changed_since(self._change_cursor)
            for key, rec in changed:
                row = self.key_to_row.get(key)
                if row is not None:
                    self._write(row, rec)

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #

    def model(self) -> dict[str, Any]:
        with self.lock:
            return {"fields": [{"name": f, "values": self._display(f)} for f in FIELDS],
                    "row_count": self.n, "history_days": self.history_days}

    def _display(self, field: str) -> list[str]:
        values = self.symbols[field]
        if field == "Event":
            return sorted((v for v in values if v != NO_EVENT)) + ([NO_EVENT] if NO_EVENT in values else [])
        if field in ("Operator", "Pay App", "Time Limit"):
            return sorted(values, key=lambda v: (v == NO_LIMIT, v))
        return list(values)

    def normalize(self, selection: Mapping[str, list[str]]) -> dict[str, list[str]]:
        """Validate a Selection, drop empty fields, and dedupe values (Req 11.1)."""
        out: dict[str, list[str]] = {}
        for f, vals in selection.items():
            if f not in self.pos:
                raise UnknownField(f)
            for v in vals:
                if v not in self.pos[f]:
                    raise UnknownValue(f, v)
            if vals:
                out[f] = list(dict.fromkeys(vals))
        return out

    def _masks(self, sel: dict[str, list[str]]) -> dict[str, np.ndarray]:
        masks = {}
        for f, vals in sel.items():
            lut = np.zeros(len(self.symbols[f]), bool)
            lut[[self.pos[f][v] for v in vals]] = True
            masks[f] = lut[self.cols[f][:self.n]]
        return masks

    def _and(self, masks: dict[str, np.ndarray], skip: str | None = None) -> np.ndarray:
        out = np.ones(self.n, bool)
        for f, m in masks.items():
            if f != skip:
                out &= m
        return out

    def query(self, selection: Mapping[str, list[str]]) -> dict[str, Any]:
        with self.lock:
            sel = self.normalize(selection)
            masks = self._masks(sel)
            assoc = self._and(masks)
            fields = []
            for f in FIELDS:
                col = self.cols[f][:self.n]
                k = len(self.symbols[f])
                asc_c = np.bincount(col[assoc], minlength=k)
                ctx_c = np.bincount(col[self._and(masks, f)], minlength=k) if f in masks else asc_c
                chosen = set(sel.get(f, ()))
                values = []
                for v in self._display(f):
                    i = self.pos[f][v]
                    values.append({"value": v, "count": int(ctx_c[i] if f in masks else asc_c[i]),
                                   "state": _state(v in chosen, f in masks, int(ctx_c[i]), int(asc_c[i]))})
                fields.append({"name": f, "values": values})
            return {"selection": sel, "fields": fields, **self._aggregates(assoc)}

    def select(self, selection: Mapping[str, list[str]], field: str, value: str) -> dict[str, Any]:
        """Apply one click to a Selection and return the new query result (Req 11.9-11.12)."""
        with self.lock:
            sel = self.normalize(selection)
            self.normalize({field: [value]})
            current = self.query(sel)
            state = next(v["state"] for fv in current["fields"] if fv["name"] == field
                         for v in fv["values"] if v["value"] == value)
            if state in ("selected", "selected_excluded"):
                rest = [v for v in sel[field] if v != value]
                if rest:
                    sel[field] = rest
                else:
                    del sel[field]
            elif state in ("possible", "alternative"):
                sel[field] = [*sel.get(field, []), value]
            else:  # excluded: keep only the other fields compatible with the clicked value
                rows = self.cols[field][:self.n] == self.pos[field][value]
                new = {field: [value]}
                for g, vals in sel.items():
                    if g != field and (rows & self._masks({g: vals})[g]).any():
                        new[g] = vals
                if not self._and(self._masks(new)).any():
                    new = {field: [value]}
                sel = new
            return self.query(sel)

    def _aggregates(self, assoc: np.ndarray) -> dict[str, Any]:
        n = int(assoc.sum())
        weeks = self.history_days / 7 if self.history_days else 1.0
        stay = self.stay_min[:self.n][assoc].astype(np.float64)
        zone_col = self.cols["Zone"][:self.n][assoc]
        slots = self.slot[:self.n][assoc]
        zones_present = np.unique(zone_col)
        cap_a = float(self.zone_cap[zones_present].sum()) if n else 0.0

        if n:
            overstay = self.cols["Outcome"][:self.n][assoc] == self.pos["Outcome"]["Overstayed"]
            distinct_slots = len(np.unique(slots))
            kpis = {"sessions": n,
                    "avg_stay_min": round(float(stay.mean()), 1),
                    "revenue": round(float(self.revenue[:self.n][assoc].astype(np.float64).sum()), 2),
                    "overstay_rate": round(float(overstay.mean()), 3),
                    "avg_occupancy": round(min(1.0, stay.sum() / 60 / (cap_a * distinct_slots * weeks)), 3)}
        else:
            kpis = {"sessions": 0, "avg_stay_min": None, "revenue": None, "overstay_rate": None,
                    "avg_occupancy": None}

        hours_by_slot = np.bincount(slots, weights=stay / 60, minlength=168)
        rows_by_slot = np.bincount(slots, minlength=168)
        cells = [[(round(min(1.0, hours_by_slot[d * 24 + h] / (cap_a * weeks)), 3)
                   if rows_by_slot[d * 24 + h] else None) for h in range(24)] for d in range(7)]

        k = len(self.symbols["Zone"])
        z_count = np.bincount(zone_col, minlength=k)
        z_stay = np.bincount(zone_col, weights=stay, minlength=k)
        days_present = len(np.unique(self.cols["Day"][:self.n][assoc])) if n else 0
        names = self.symbols["Zone"]
        by_zone = sorted(((names[i], int(z_count[i])) for i in range(k) if z_count[i]), key=lambda t: (-t[1], t[0]))
        turnover = []
        for i in range(k):
            if z_count[i]:
                denom = self.zone_cap[i] * self.history_days * days_present / 7
                turnover.append({"zone": names[i],
                                 "sessions_per_space_per_day": round(z_count[i] / denom, 2) if denom else 0.0,
                                 "avg_stay_min": round(z_stay[i] / z_count[i], 1)})
        turnover.sort(key=lambda t: (-t["sessions_per_space_per_day"], t["zone"]))
        bucket_counts = np.bincount(self.cols["Stay Length"][:self.n][assoc], minlength=len(STAY_BUCKETS))
        return {
            "kpis": kpis,
            "heatmap": {"days": DAYS, "hours": list(range(24)), "cells": cells},
            "charts": {
                "sessions_by_zone": [{"zone": z, "sessions": c} for z, c in by_zone],
                "stay_length": [{"bucket": b, "sessions": int(bucket_counts[self.pos["Stay Length"][b]])}
                                for b in STAY_BUCKETS],
                "turnover": turnover,
            },
        }



__all__ = ["FIELDS", "AssociativeEngine", "UnknownField", "UnknownValue", "outcome", "stay_bucket", "time_of_week"]
