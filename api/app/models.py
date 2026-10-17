"""Response models. These must match fixtures/sample_responses.json (the API contract)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class LatLng(BaseModel):
    lat: float
    lng: float


class ZoneStatus(BaseModel):
    zone_id: int
    occupied: int
    opening_soon: int
    updated_at: datetime


class Prediction(BaseModel):
    zone_id: int
    at: datetime
    expected_occupancy: float
    prob_available: float
    expected_open: int


class OpeningSoonZone(BaseModel):
    zone_id: int
    name: str
    opening_soon: int
    walk_minutes: int
    pay_app: str


class OpeningSoon(BaseModel):
    near: LatLng
    within_minutes: int
    zones: list[OpeningSoonZone]


class DestinationRef(BaseModel):
    destination_id: int
    name: str


class RecommendOption(BaseModel):
    rank: int
    zone_id: int
    name: str
    prob_available: float
    expected_open: int
    hourly_rate: float | None
    time_limit_min: int | None
    walk_minutes: int
    pay_app: str
    score: float


class Recommendation(BaseModel):
    destination: DestinationRef
    arrival: datetime
    options: list[RecommendOption]


Scenario = Literal["game_day", "family_weekend", "clear"]


class ScenarioRequest(BaseModel):
    scenario: Scenario


class ScenarioResult(BaseModel):
    scenario: Scenario
    event_id: int | None
    message: str
