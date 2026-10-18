"""Session_Source seam: the only way the API and engine read Sessions (Req 18.1-18.4).

``SessionSource`` is the adapter interface. ``SimulatorSource`` is the only
implementation in the local build (Req 18.2). A real adapter replaces it without
touching any route, engine, or UI code.

Privacy rule (Req 18.4): every adapter MUST drop license plates and personal
identifiers (names, phone numbers, emails, account or payment IDs) before it
builds a ``SessionRecord``. The record carries only the five Req 18.3 fields, so
nothing else can reach the engine or the Data_Store.

Planned adapters, documented in ``docs/integration.md``:

- ``PassportSource``: Lehigh Parking Services through the Passport partner REST
  API, using OAuth client credentials issued to approved partners. The
  parking-environment export maps to Zone and Rate_Rule; session events map to
  Session.
- ``ParkMobileSource``: BPA on-street Sessions through the gated ParkMobile
  partner developer portal. BPA also accepts PayByPhone, so ParkMobile alone
  undercounts.

Cursors and keys
----------------
Both methods take an integer cursor (start at 0) and return ``(items,
new_cursor)``; pass ``new_cursor`` back on the next call. Each item is ``(key,
record)``. Keys are opaque integers used only for in-engine row updates and
never leave the API.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # avoid a runtime import cycle; only the types are needed
    from .data import Session
    from .sim import Simulator

__all__ = ["SessionRecord", "SessionSource", "SimulatorSource", "to_record"]


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """One parking session, with exactly the Req 18.3 fields and no person identifiers."""

    zone_id: str
    start_time: datetime
    paid_until: datetime
    end_time: datetime
    event_id: str | None


@runtime_checkable
class SessionSource(Protocol):
    """Adapter interface for reading Sessions (Req 18.1).

    Adapters MUST drop license plates and personal identifiers before building a
    ``SessionRecord`` (Req 18.4).
    """

    def sessions_since(self, cursor: int) -> tuple[list[tuple[int, SessionRecord]], int]:
        """Sessions added after `cursor`, in arrival order, plus the new cursor."""
        ...

    def changed_since(self, cursor: int) -> tuple[list[tuple[int, SessionRecord]], int]:
        """Sessions whose fields changed after `cursor` (for example, End_Time moved by
        a scenario reset), with their current values, each key once, plus the new cursor.

        A key here may not have been returned by ``sessions_since`` yet. A later
        ``sessions_since`` call returns it with its current values, so consumers
        can skip keys they don't hold.
        """
        ...


def to_record(session: Session) -> SessionRecord:
    """Copy the five Req 18.3 fields of a simulator Session into a SessionRecord."""
    return SessionRecord(
        zone_id=session.zone_id,
        start_time=session.start_time,
        paid_until=session.paid_until,
        end_time=session.end_time,
        event_id=session.event_id,
    )


def _check_cursor(cursor: int, end: int, what: str) -> None:
    if isinstance(cursor, bool) or not isinstance(cursor, int) or not 0 <= cursor <= end:
        raise ValueError(f"{what} cursor must be an integer in [0, {end}], got {cursor!r}")


class SimulatorSource:
    """SessionSource backed by a Simulator's Session table and change log (Req 18.2).

    Keys are ``session_id`` values (the index in ``sim.sessions``). The session
    cursor is a position in ``sim.sessions``; the change cursor is a position in
    the append-only ``sim.change_log``. Reads hold ``sim.lock`` so each batch is
    a consistent view.
    """

    __slots__ = ("_sim",)

    def __init__(self, sim: Simulator) -> None:
        self._sim = sim

    @property
    def history_days(self) -> int:
        """Days of generated history behind the simulator's start."""
        return self._sim.history_days

    @property
    def simulated_through(self) -> datetime:
        """The simulation clock (UTC): every session starting before it has been generated."""
        return self._sim.simulated_through

    def sessions_since(self, cursor: int) -> tuple[list[tuple[int, SessionRecord]], int]:
        with self._sim.lock:
            sessions = self._sim.sessions
            end = len(sessions)
            _check_cursor(cursor, end, "session")
            items = [(k, to_record(sessions[k])) for k in range(cursor, end)]
        return items, end

    def changed_since(self, cursor: int) -> tuple[list[tuple[int, SessionRecord]], int]:
        with self._sim.lock:
            log = self._sim.change_log
            end = len(log)
            _check_cursor(cursor, end, "change")
            # Dedupe, keeping each key at the position of its last change.
            order: dict[int, None] = {}
            for k in log[cursor:end]:
                order.pop(k, None)
                order[k] = None
            sessions = self._sim.sessions
            items = [(k, to_record(sessions[k])) for k in order]
        return items, end
