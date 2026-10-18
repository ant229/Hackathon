"""Server-Sent Events fan-out for live Zone_Status updates (Req 13.8, 15.2-15.5).

This module is independent of the simulator. Rows are plain JSON-serializable
dicts (for Zone_Status: ``zone_id``, ``occupied``, ``active_sessions``,
``opening_soon``, ``updated_at``); ``datetime`` values are serialized with
``isoformat()``.

Wire format (one JSON line per ``data:`` field)::

    event: snapshot
    data: {"zones":[...every row...]}

    event: status
    data: {"zones":[...changed rows...]}

    : heartbeat

Threading model: each subscriber queue belongs to the event loop that called
``subscribe()``. ``publish()`` may run on that loop's thread (the ticker) or on
any worker thread (scenario routes in the threadpool). It always hands delivery
to the subscriber's loop with ``loop.call_soon_threadsafe``, so deliveries keep
the global publish order no matter which thread published.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from datetime import date, datetime, time
from typing import Any, Final

__all__ = [
    "DEFAULT_HEARTBEAT_S",
    "HEARTBEAT",
    "QUEUE_MAXSIZE",
    "SNAPSHOT_EVENT",
    "SNAPSHOT_MARKER",
    "SSE_HEADERS",
    "SSE_MEDIA_TYPE",
    "STATUS_EVENT",
    "Broadcaster",
    "encode_json",
    "event_stream",
    "format_sse",
]

QUEUE_MAXSIZE: Final = 100
DEFAULT_HEARTBEAT_S: Final = 15.0
DEFAULT_DISCONNECT_POLL_S: Final = 1.0

SNAPSHOT_EVENT: Final = "snapshot"
STATUS_EVENT: Final = "status"
HEARTBEAT: Final = ": heartbeat\n\n"

SSE_MEDIA_TYPE: Final = "text/event-stream"
SSE_HEADERS: Final[Mapping[str, str]] = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

Row = Mapping[str, Any]
SnapshotFn = Callable[[], Iterable[Row] | Awaitable[Iterable[Row]]]
DisconnectFn = Callable[[], Awaitable[bool]]


class _SnapshotMarker:
    """Queue item telling a reader to send a fresh full snapshot."""

    _instance: _SnapshotMarker | None = None

    def __new__(cls) -> _SnapshotMarker:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "SNAPSHOT_MARKER"


SNAPSHOT_MARKER: Final = _SnapshotMarker()


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    tolist = getattr(obj, "tolist", None)  # numpy scalars and arrays, without importing numpy
    if callable(tolist):
        return tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def encode_json(data: Any) -> str:
    """Compact JSON (no spaces, no NaN) with datetimes as ISO 8601 strings."""
    return json.dumps(data, default=_json_default, separators=(",", ":"), allow_nan=False)


def format_sse(event: str, data: Any) -> str:
    """Format one SSE message.

    ``data`` that is a ``str`` is sent as-is (already encoded); anything else is
    JSON-encoded with :func:`encode_json`. Multi-line data becomes one ``data:``
    line per line, as the SSE spec requires.
    """
    if not event or any(c in event for c in "\r\n:"):
        raise ValueError(f"Invalid SSE event name: {event!r}")
    text = data if isinstance(data, str) else encode_json(data)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"


# --------------------------------------------------------------------------- #
# Broadcaster
# --------------------------------------------------------------------------- #


class Broadcaster:
    """Fans changed rows out to every subscribed ``/stream`` client.

    Each subscriber gets a bounded ``asyncio.Queue``. When a slow client's queue
    is full, it is cleared and a ``SNAPSHOT_MARKER`` is enqueued, so that client
    receives one fresh full snapshot instead of a backlog.
    """

    def __init__(self, maxsize: int = QUEUE_MAXSIZE) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._subs: dict[asyncio.Queue[Any], asyncio.AbstractEventLoop] = {}

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def subscribe(self) -> asyncio.Queue[Any]:
        """Register a new subscriber on the running event loop.

        Must be called from inside a running loop; the loop is bound lazily
        here, so no explicit attach step is needed in the app lifespan.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._maxsize)
        with self._lock:
            self._subs[queue] = loop
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Any]) -> None:
        """Remove a subscriber. Safe to call more than once."""
        with self._lock:
            self._subs.pop(queue, None)

    def publish(self, rows: Iterable[Row]) -> int:
        """Send changed rows to every subscriber. Thread-safe.

        The payload is encoded once, on the caller's thread, so later mutation
        of ``rows`` cannot leak into the stream. An empty ``rows`` sends
        nothing. Returns the number of subscribers the payload was scheduled for.
        """
        rows = list(rows)
        if not rows:
            return 0
        with self._lock:
            targets = list(self._subs.items())
        if not targets:
            return 0
        payload = encode_json({"zones": rows})

        by_loop: dict[asyncio.AbstractEventLoop, list[asyncio.Queue[Any]]] = {}
        for queue, loop in targets:
            by_loop.setdefault(loop, []).append(queue)

        scheduled = 0
        for loop, queues in by_loop.items():
            try:
                loop.call_soon_threadsafe(self._deliver, queues, payload)
            except RuntimeError:  # the subscriber's loop is closed; drop its queues
                with self._lock:
                    for queue in queues:
                        self._subs.pop(queue, None)
                continue
            scheduled += len(queues)
        return scheduled

    def _deliver(self, queues: list[asyncio.Queue[Any]], payload: str) -> None:
        """Runs on the subscribers' loop thread."""
        for queue in queues:
            with self._lock:
                if queue not in self._subs:  # unsubscribed after publish was scheduled
                    continue
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                _drain(queue)
                queue.put_nowait(SNAPSHOT_MARKER)


def _drain(queue: asyncio.Queue[Any]) -> None:
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return


# --------------------------------------------------------------------------- #
# SSE generator
# --------------------------------------------------------------------------- #


async def _snapshot_message(snapshot_fn: SnapshotFn) -> str:
    rows = snapshot_fn()
    if inspect.isawaitable(rows):
        rows = await rows
    return format_sse(SNAPSHOT_EVENT, {"zones": list(rows)})


async def event_stream(
    broadcaster: Broadcaster,
    snapshot_fn: SnapshotFn,
    *,
    heartbeat_s: float = DEFAULT_HEARTBEAT_S,
    max_events: int | None = None,
    is_disconnected: DisconnectFn | None = None,
    disconnect_poll_s: float = DEFAULT_DISCONNECT_POLL_S,
) -> AsyncIterator[str]:
    """Yield SSE text for one ``/stream`` client.

    - First ``event: snapshot`` with every row from ``snapshot_fn()`` (sync, or
      async returning the rows). The subscription is registered before the
      snapshot is read, so no change published in between is lost.
    - Then ``event: status`` with the changed rows of each publish, or a fresh
      ``event: snapshot`` if this client's queue overflowed.
    - ``: heartbeat`` after ``heartbeat_s`` seconds without any message.
    - Stops after ``max_events`` events (snapshot and status count; heartbeats
      don't), or when ``await is_disconnected()`` is true. That callable (for
      example ``request.is_disconnected``) is polled at least every
      ``disconnect_poll_s`` seconds while idle.
    - Always unsubscribes on exit, including cancellation and ``aclose()``.
    """
    if heartbeat_s <= 0:
        raise ValueError("heartbeat_s must be positive")
    if disconnect_poll_s <= 0:
        raise ValueError("disconnect_poll_s must be positive")
    if max_events is not None and max_events < 0:
        raise ValueError("max_events must be non-negative")

    queue = broadcaster.subscribe()
    try:
        if max_events == 0:
            return
        clock = asyncio.get_running_loop().time

        yield await _snapshot_message(snapshot_fn)
        sent = 1
        last_sent = clock()

        while max_events is None or sent < max_events:
            if is_disconnected is not None and await is_disconnected():
                return
            remaining = heartbeat_s - (clock() - last_sent)
            if remaining <= 0:
                yield HEARTBEAT
                last_sent = clock()
                continue
            wait = remaining if is_disconnected is None else min(remaining, disconnect_poll_s)
            try:
                async with asyncio.timeout(wait):
                    item = await queue.get()
            except TimeoutError:
                continue

            if item is SNAPSHOT_MARKER:
                message = await _snapshot_message(snapshot_fn)
            else:
                message = format_sse(STATUS_EVENT, item)
            yield message
            sent += 1
            last_sent = clock()
    finally:
        broadcaster.unsubscribe(queue)
