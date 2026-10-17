// Mirrors fixtures/sample_responses.json and the API's Pydantic models (api/app/models.py).

export type ZoneProps = {
  zone_id: number;
  name: string;
  facility: string;
  facility_type: "garage" | "lot" | "street";
  operator: string;
  pay_app: string;
  capacity: number;
  visitor_allowed: boolean;
  hourly_rate: number | null;
  time_limit_min: number | null;
};

export type Zone = ZoneProps & { lat: number; lng: number };

export type ZoneStatus = {
  zone_id: number;
  occupied: number;
  opening_soon: number;
  updated_at: string;
};

export type RecommendOption = {
  rank: number;
  zone_id: number;
  name: string;
  prob_available: number;
  expected_open: number;
  hourly_rate: number | null;
  time_limit_min: number | null;
  walk_minutes: number;
  pay_app: string;
  score: number;
};

export type Recommendation = {
  destination: { destination_id: number; name: string };
  arrival: string;
  options: RecommendOption[];
};
