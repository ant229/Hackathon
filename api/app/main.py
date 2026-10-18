"""SpotStack Analytics API (Req 15).

One process runs everything for the local build: the Simulator (mock sessions),
the AssociativeEngine fed through the Session_Source seam (Req 18.1), and the
SSE Broadcaster. A ticker advances the simulation every 2 s.

Start from api/:  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
No auth by design in the local build, including /demo/scenario.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .associative import AssociativeEngine, UnknownField, UnknownValue
from .data import SEED_PATH, TZ, applicable_rule, haversine_m, walk_minutes
from .sim import Simulator, UnknownScenario, build_simulator
from .sources import SimulatorSource
from .stream import SSE_HEADERS, SSE_MEDIA_TYPE, Broadcaster, event_stream

log = logging.getLogger(__name__)

TICK_SECONDS = 2.0
WEIGHTS = {"availability": 0.5, "price": 0.2, "walk": 0.3}
MAX_WALK_MINUTES = 25
MIN_CANDIDATES = 3
OPENING_SOON_WINDOW_MIN = 15


class ApiError(Exception):
    def __init__(self, status: int, error: str, message: str, **extra):
        self.status, self.body = status, {"error": error, "message": message, **extra}


class ScenarioRequest(BaseModel):
    scenario: str  # str, not Literal, so unknown names reach the 400 path


class QueryRequest(BaseModel):
    selection: dict[str, list[str]] = {}


class SelectRequest(QueryRequest):
    field: str
    value: str


def _local(ts: datetime) -> datetime:
    """Naive times are America/New_York (design: Times)."""
    return ts.replace(tzinfo=TZ) if ts.tzinfo is None else ts.astimezone(TZ)


def _iso(ts: datetime) -> str:
    return ts.astimezone(TZ).isoformat()


def _status_row(row) -> dict:
    return {"zone_id": row.zone_id, "occupied": round(row.occupied, 4), "active_sessions": row.active_sessions,
            "opening_soon": row.opening_soon, "updated_at": _iso(row.updated_at)}


def create_app(sim: Simulator | None = None, clock: Callable[[], datetime] | None = None,
               run_ticker: bool = True) -> FastAPI:
    now: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
    broadcaster = Broadcaster()
    state: dict = {"sim": sim, "engine": None}

    def get_sim() -> Simulator:
        return state["sim"]

    def get_engine() -> AssociativeEngine:
        return state["engine"]

    def start() -> None:
        if state["sim"] is None:
            s = build_simulator(Path(os.environ.get("SEED_PATH", SEED_PATH)), start=now(),
                                history_days=int(os.environ.get("HISTORY_DAYS", 28)),
                                rng_seed=int(os.environ.get("SIM_RNG_SEED", 7)))
            s.generate_history()
            state["sim"] = s
        engine = AssociativeEngine(get_sim().store, get_sim().history_days)
        engine.load(SimulatorSource(get_sim()))
        state["engine"] = engine

    def tick() -> None:
        changed = get_sim().advance_to(now())
        if changed:
            broadcaster.publish([_status_row(r) for r in changed])
        get_engine().sync()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await asyncio.to_thread(start)
        task = None
        if run_ticker:
            async def ticker():
                while True:
                    await asyncio.sleep(TICK_SECONDS)
                    try:
                        await asyncio.to_thread(tick)
                    except Exception:  # noqa: BLE001 - log and retry next tick
                        log.exception("ticker failed")
            task = asyncio.create_task(ticker())
        yield
        if task:
            task.cancel()

    app = FastAPI(title="SpotStack API", lifespan=lifespan)
    app.state.heartbeat_s = 15.0
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=exc.body)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        err = exc.errors()[0]
        param = str(err["loc"][-1]) if err.get("loc") else "body"
        if err.get("type") == "missing":
            body = {"error": "missing_parameter", "parameter": param,
                    "message": f"Add the '{param}' parameter and try again."}
        else:
            body = {"error": "invalid_parameter", "parameter": param,
                    "message": f"Fix the '{param}' parameter: {err.get('msg', 'invalid value')}."}
        return JSONResponse(status_code=422, content=body)

    def store():
        return get_sim().store

    def zone_meta(zid: str) -> dict:
        st = store()
        z = st.zones[zid]
        fac = st.facilities[z.facility_id]
        op = st.operators[fac.operator_id]
        return {"zone_id": zid, "zone_name": z.name, "facility_name": fac.name, "operator": op.name,
                "pay_app": list(op.pay_app), "note": z.note}

    def rule_fields(zid: str, ts: datetime) -> dict:
        rule = applicable_rule(store(), zid, ts)
        return {"hourly_rate": rule.hourly_rate if rule else 0, "time_limit_min": rule.time_limit_min if rule else None,
                "enforced": rule is not None}

    # ------------------------------------------------------------------ read

    @app.get("/health")
    def health():
        s = get_sim()
        return {"status": "ok", "zones": len(s.store.zones), "sessions": len(s.sessions),
                "simulated_through": _iso(s.simulated_through)}

    @app.get("/zones")
    def zones():
        ts = now()
        status = get_sim().zone_status()
        out = []
        for zid, z in store().zones.items():
            fac = store().facilities[z.facility_id]
            row = _status_row(status[zid])
            row.pop("zone_id")
            out.append({**zone_meta(zid), "facility_type": fac.type, "lat": fac.lat, "lng": fac.lng,
                        "capacity": z.capacity, "visitor_allowed": z.visitor_allowed, **rule_fields(zid, ts),
                        "status": row})
        return {"zones": out}

    @app.get("/stream")
    async def stream(request: Request, max_events: int | None = Query(None, ge=0)):
        def snapshot():
            return [_status_row(r) for r in get_sim().zone_status().values()]
        gen = event_stream(broadcaster, snapshot, heartbeat_s=app.state.heartbeat_s, max_events=max_events,
                           is_disconnected=request.is_disconnected)
        return StreamingResponse(gen, media_type=SSE_MEDIA_TYPE, headers=dict(SSE_HEADERS))

    @app.get("/destinations")
    def destinations():
        return {"destinations": [{"destination_id": d.destination_id, "name": d.name, "lat": d.lat, "lng": d.lng}
                                 for d in store().destinations.values()]}

    @app.get("/predict")
    def predict(zone: str = Query(...), time: datetime = Query(...)):
        if zone not in store().zones:
            raise ApiError(404, "not_found", f"No zone with ID '{zone}'.")
        p = get_sim().predict(zone, _local(time))
        return {"zone_id": zone, "zone_name": store().zones[zone].name, "time": _iso(p.time),
                "hour_of_week": p.hour_of_week, "baseline_occupancy": round(p.baseline_occupancy, 4),
                "event_boost": p.event_boost, "event_name": p.event_name,
                "predicted_occupancy": round(p.predicted_occupancy, 4),
                "predicted_availability": round(p.predicted_availability, 4)}

    @app.get("/opening-soon")
    def opening_soon(near: str = Query(...)):
        try:
            lat_s, lng_s = near.split(",")
            lat, lng = float(lat_s), float(lng_s)
            if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError
        except ValueError:
            raise ApiError(422, "invalid_parameter",
                           "Use 'near=lat,lng' with two decimal numbers, for example 40.607,-75.378.",
                           parameter="near") from None
        ts = now()
        results = []
        for zid, count in get_sim().opening_soon_counts(ts).items():
            if count <= 0:
                continue
            fac = store().facilities[store().zones[zid].facility_id]
            dist = haversine_m(lat, lng, fac.lat, fac.lng)
            meta = zone_meta(zid)
            results.append({"zone_id": zid, "zone_name": meta["zone_name"], "facility_name": meta["facility_name"],
                            "opening_soon": count, "distance_m": round(dist, 1), "walk_minutes": walk_minutes(dist)})
        results.sort(key=lambda r: (r["distance_m"], r["zone_id"]))
        return {"near": {"lat": lat, "lng": lng}, "evaluated_at": _iso(ts),
                "window_minutes": OPENING_SOON_WINDOW_MIN, "results": results}

    @app.get("/recommend")
    def recommend(destination: str = Query(...), arrival: datetime = Query(...),
                  limit: int = Query(5, ge=1, le=20)):
        dest = store().destinations.get(destination)
        if dest is None:
            raise ApiError(404, "not_found", f"No destination with ID '{destination}'.")
        arrival = _local(arrival)
        everyone = []
        for zid, z in store().zones.items():
            if not z.visitor_allowed:
                continue
            fac = store().facilities[z.facility_id]
            dist = haversine_m(dest.lat, dest.lng, fac.lat, fac.lng)
            everyone.append((walk_minutes(dist), dist, zid))
        everyone.sort()
        candidates = [c for c in everyone if c[0] <= MAX_WALK_MINUTES]
        if len(candidates) < MIN_CANDIDATES:
            candidates += [c for c in everyone if c[0] > MAX_WALK_MINUTES][:MIN_CANDIDATES - len(candidates)]

        rows = []
        for walk, dist, zid in candidates:
            p = get_sim().predict(zid, arrival)
            row = {**zone_meta(zid), **rule_fields(zid, arrival), "distance_m": round(dist, 1),
                   "walk_minutes": walk, "within_walk_limit": walk <= MAX_WALK_MINUTES,
                   "predicted_availability": round(p.predicted_availability, 4)}
            row["event_warning"] = ({"event_name": p.event_name, "start_time": _iso(p.event_start)}
                                    if p.event_boost > 1.0 and p.event_name else None)
            rows.append(row)

        def inverse_norm(key: str) -> list[float]:
            vals = [r[key] for r in rows]
            lo, hi = min(vals, default=0), max(vals, default=0)
            return [1.0 if hi == lo else 1 - (v - lo) / (hi - lo) for v in vals]

        for r, price, walk in zip(rows, inverse_norm("hourly_rate"), inverse_norm("walk_minutes")):
            r["price_score"], r["walk_score"] = round(price, 4), round(walk, 4)
            r["score"] = round(WEIGHTS["availability"] * r["predicted_availability"]
                               + WEIGHTS["price"] * price + WEIGHTS["walk"] * walk, 4)
        rows.sort(key=lambda r: (-r["score"], r["walk_minutes"], r["zone_id"]))
        results = [{"rank": i + 1, **r} for i, r in enumerate(rows[:limit])]
        return {"destination": {"destination_id": dest.destination_id, "name": dest.name},
                "arrival": _iso(arrival), "weights": WEIGHTS, "max_walk_minutes": MAX_WALK_MINUTES,
                "results": results}

    # ------------------------------------------------------------------ demo

    @app.post("/demo/scenario")
    def demo_scenario(req: ScenarioRequest):
        try:
            result = get_sim().apply_scenario(req.scenario, now())
        except UnknownScenario as exc:
            raise ApiError(400, "unknown_scenario", f"Scenario '{exc.name}' is not available.",
                           allowed=exc.allowed) from None
        if result.changed:
            broadcaster.publish([_status_row(r) for r in result.changed])
        get_engine().sync()
        event = None
        if result.event is not None:
            event = {"event_id": result.event.event_id, "name": result.event.name,
                     "start_time": _iso(result.event.start_time), "expires_at": _iso(result.expires_at)}
        return {"scenario": result.scenario, "event": event, "affected": result.affected}

    @app.get("/demo/status")
    def demo_status():
        active = get_sim().scenario_status(now())
        if active:
            active = {**active, "triggered_at": _iso(active["triggered_at"]),
                      "expires_at": _iso(active["expires_at"])}
        return {"active": active}

    # ------------------------------------------------------------------ explore

    def explore(fn):
        try:
            return fn()
        except UnknownField as exc:
            raise ApiError(422, "invalid_parameter", str(exc), parameter=exc.field) from None
        except UnknownValue as exc:
            raise ApiError(422, "invalid_parameter", str(exc), parameter=exc.field) from None

    @app.get("/explore/model")
    def explore_model():
        return get_engine().model()

    @app.post("/explore/query")
    def explore_query(req: QueryRequest):
        return explore(lambda: get_engine().query(req.selection))

    @app.post("/explore/select")
    def explore_select(req: SelectRequest):
        return explore(lambda: get_engine().select(req.selection, req.field, req.value))

    app.state.get_sim, app.state.get_engine, app.state.tick = get_sim, get_engine, tick
    return app


app = create_app()

__all__ = ["app", "create_app"]
