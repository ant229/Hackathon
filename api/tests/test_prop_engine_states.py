"""Property 14: Selection evaluation matches the reference definitions (Req 11.1-11.7).

*For any* session set and Selection over existing Field_Values, the engine's
Associated_Rows equal a brute-force filter that ORs within a Field and ANDs
across Fields, and every Field_Value's Value_State equals the reference
classification computed from the Field's Field_Context and the Associated_Rows.

The oracle is independent of the engine's numpy bincount path:

- It derives each row's value in every field straight from the ``SessionRecord``
  and the seed store, following the design's derivation table. (Field
  derivations are checked on their own by Property 13; here they just give the
  oracle honest per-row values.)
- Associated_Rows = rows where, for every field with a Selection, the row's
  value is one of that field's selected values (OR within a field, AND across
  fields) (Req 11.1).
- Field_Context for field F = rows satisfying the Selection in every field
  except F.
- The five states follow the design's ``state`` definition directly
  (Req 11.3-11.7):
    - Selected: value is selected AND its Field_Context count > 0.
    - Selected_Excluded: value is selected AND its Field_Context count == 0.
    - Possible: not selected AND it occurs in >= 1 Associated_Row.
    - Alternative: not selected AND the field has a Selection AND its
      Field_Context count > 0.
    - Excluded: otherwise.

Selections are drawn from the values actually present in each generated record
set, so most examples carry real selections across one, two, or three fields.
"""
from __future__ import annotations

from collections import Counter

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.associative import (
    DAYS,
    FIELDS,
    NO_EVENT,
    NO_LIMIT,
    stay_bucket,
    time_of_week,
)
from app.data import TZ, applicable_rule
from app.sources import SessionRecord

from .engine_support import build_engine, seed_store, session_records

OUTCOME_GRACE_MIN = 5.0


# --------------------------------------------------------------------------- #
# Oracle: derive each row's value per field straight from the record + store.
# --------------------------------------------------------------------------- #

_STORE = seed_store()


def _oracle_outcome(rec: SessionRecord) -> str:
    delta_min = (rec.end_time - rec.paid_until).total_seconds() / 60
    if delta_min < -OUTCOME_GRACE_MIN:
        return "Left Early"
    if delta_min > OUTCOME_GRACE_MIN:
        return "Overstayed"
    return "On Time"


def _oracle_values(rec: SessionRecord) -> dict[str, str]:
    """The value of every field for one session, matching the design table."""
    store = _STORE
    zone = store.zones[rec.zone_id]
    facility = store.facilities[zone.facility_id]
    operator = store.operators[facility.operator_id]
    local = rec.start_time.astimezone(TZ)
    rule = applicable_rule(store, rec.zone_id, rec.start_time)
    event = store.events.get(rec.event_id) if rec.event_id else None
    stay_min = (rec.end_time - rec.start_time).total_seconds() / 60
    return {
        "Zone": zone.name,
        "Facility Type": facility.type.title(),
        "Operator": operator.name,
        "Pay App": " / ".join(operator.pay_app),
        "Visitor Access": "Visitors Allowed" if zone.visitor_allowed else "Permit Only",
        "Day": DAYS[local.weekday()],
        "Arrival Hour": str(local.hour),
        "Time of Week": time_of_week(local.weekday(), local.hour),
        "Event": event.name if event else NO_EVENT,
        "Stay Length": stay_bucket(stay_min),
        "Outcome": _oracle_outcome(rec),
        "Time Limit": (
            f"{rule.time_limit_min / 60:g} H" if rule and rule.time_limit_min else NO_LIMIT
        ),
    }


def _row_values(records: list[SessionRecord]) -> list[dict[str, str]]:
    return [_oracle_values(rec) for rec in records]


def _row_matches_field(row: dict[str, str], field: str, selected: list[str]) -> bool:
    """OR within a field: True when the row's value is one of the selected values."""
    return row[field] in selected


def _associated_rows(
    rows: list[dict[str, str]], selection: dict[str, list[str]]
) -> list[dict[str, str]]:
    """AND across fields of the per-field OR masks (Req 11.1)."""
    return [
        row
        for row in rows
        if all(_row_matches_field(row, f, vals) for f, vals in selection.items())
    ]


def _field_context(
    rows: list[dict[str, str]], selection: dict[str, list[str]], field: str
) -> list[dict[str, str]]:
    """Rows satisfying the Selection in every field except ``field``."""
    return [
        row
        for row in rows
        if all(
            _row_matches_field(row, f, vals)
            for f, vals in selection.items()
            if f != field
        )
    ]


def _reference_state(
    value: str,
    selected: bool,
    field_has_sel: bool,
    ctx_count: int,
    assoc_count: int,
) -> str:
    if selected:
        return "selected" if ctx_count > 0 else "selected_excluded"
    if assoc_count > 0:
        return "possible"
    if field_has_sel and ctx_count > 0:
        return "alternative"
    return "excluded"


# --------------------------------------------------------------------------- #
# Selection strategy: pick fields and values that exist in the record set.
# --------------------------------------------------------------------------- #


@st.composite
def _selection(draw: st.DrawFn, records: list[SessionRecord]) -> dict[str, list[str]]:
    if not records:
        return {}
    rows = _row_values(records)
    present: dict[str, list[str]] = {}
    for f in FIELDS:
        values = sorted({row[f] for row in rows})
        if values:
            present[f] = values
    if not present:
        return {}
    fields = draw(
        st.lists(st.sampled_from(sorted(present)), min_size=0, max_size=3, unique=True)
    )
    selection: dict[str, list[str]] = {}
    for f in fields:
        chosen = draw(
            st.lists(st.sampled_from(present[f]), min_size=1, max_size=3, unique=True)
        )
        selection[f] = chosen
    return selection


@st.composite
def _records_and_selection(
    draw: st.DrawFn,
) -> tuple[list[SessionRecord], dict[str, list[str]]]:
    records = draw(session_records(min_size=1, max_size=40))
    selection = draw(_selection(records))
    return records, selection


# --------------------------------------------------------------------------- #
# The property.
# --------------------------------------------------------------------------- #


# Feature: parking-monitor, Property 14: Selection evaluation matches the reference definitions
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=_records_and_selection())
def test_selection_evaluation_matches_reference(
    data: tuple[list[SessionRecord], dict[str, list[str]]],
) -> None:
    """**Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7**"""
    records, selection = data
    engine = build_engine(records)
    result = engine.query(selection)

    rows = _row_values(records)

    # Req 11.1: Associated_Rows = OR within a field, AND across fields.
    assoc = _associated_rows(rows, selection)
    assert result["kpis"]["sessions"] == len(assoc), (
        f"associated row count {result['kpis']['sessions']} != oracle {len(assoc)} "
        f"for selection {selection}"
    )

    # Precompute oracle counts over Associated_Rows and each Field_Context.
    assoc_counts: dict[str, Counter[str]] = {
        f: Counter(row[f] for row in assoc) for f in FIELDS
    }
    ctx_counts: dict[str, Counter[str]] = {
        f: Counter(row[f] for row in _field_context(rows, selection, f)) for f in FIELDS
    }

    engine_fields = {fv["name"]: fv["values"] for fv in result["fields"]}

    for f in FIELDS:
        field_has_sel = f in selection
        selected_values = set(selection.get(f, ()))
        for entry in engine_fields[f]:
            value = entry["value"]
            selected = value in selected_values
            ctx_count = ctx_counts[f][value]
            assoc_count = assoc_counts[f][value]

            expected_state = _reference_state(
                value, selected, field_has_sel, ctx_count, assoc_count
            )
            # Req 11.3-11.7: every value's state matches the reference classifier.
            assert entry["state"] == expected_state, (
                f"field {f!r} value {value!r}: engine state {entry['state']!r} != "
                f"reference {expected_state!r} (selected={selected}, "
                f"field_has_sel={field_has_sel}, ctx={ctx_count}, assoc={assoc_count}); "
                f"selection={selection}"
            )

            # The displayed count is the Field_Context count for a selected
            # field, otherwise the Associated_Rows count (design evaluate()).
            expected_count = ctx_count if field_has_sel else assoc_count
            assert entry["count"] == expected_count, (
                f"field {f!r} value {value!r}: engine count {entry['count']} != "
                f"reference {expected_count}; selection={selection}"
            )


# Feature: parking-monitor, Property 14: Selection evaluation matches the reference definitions
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(records=session_records(min_size=1, max_size=40))
def test_empty_selection_makes_every_present_value_possible(
    records: list[SessionRecord],
) -> None:
    """With no Selection, Associated_Rows is every row and present values are Possible.

    **Validates: Requirements 11.1, 11.5, 11.7**
    """
    engine = build_engine(records)
    result = engine.query({})

    rows = _row_values(records)
    assert result["kpis"]["sessions"] == len(rows)

    present = {f: Counter(row[f] for row in rows) for f in FIELDS}
    for fv in result["fields"]:
        f = fv["name"]
        for entry in fv["values"]:
            if present[f][entry["value"]] > 0:
                assert entry["state"] == "possible"
                assert entry["count"] == present[f][entry["value"]]
            else:
                assert entry["state"] == "excluded"
                assert entry["count"] == 0
