// Typed client for the Park LU Analytics_API.
// Types mirror the API contract in .kiro/specs/parking-monitor/design.md exactly
// (snake_case fields). Responses carry aggregates only: no session IDs or plates.
import { API_START_COMMAND } from "./format";

/** API base URL from NEXT_PUBLIC_API_URL, default http://localhost:8000, no trailing slash (Req 20.6). */
export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

/** Server-Sent Events endpoint for live Zone_Status updates. */
export const STREAM_URL = `${API_BASE}/stream`;

// ---------------------------------------------------------------------------
// Zones, stream, health
// ---------------------------------------------------------------------------

export type FacilityType = "garage" | "lot" | "street";

export type ZoneStatus = {
  /** Active sessions ÷ capacity, 0.0–1.0. */
  occupied: number;
  active_sessions: number;
  opening_soon: number;
  /** ISO 8601 with offset. */
  updated_at: string;
};

/** One Zone_Status row as sent on /stream (`snapshot` and `status` events). */
export type ZoneStatusRow = ZoneStatus & { zone_id: string };

/** Payload of a /stream `snapshot` or `status` event. */
export type StreamPayload = { zones: ZoneStatusRow[] };

export type Zone = {
  zone_id: string;
  zone_name: string;
  facility_name: string;
  facility_type: FacilityType;
  operator: string;
  pay_app: string[];
  note: string | null;
  lat: number;
  lng: number;
  capacity: number;
  visitor_allowed: boolean;
  /** Rate of the rule applicable now (0 when no rule applies). */
  hourly_rate: number;
  time_limit_min: number | null;
  enforced: boolean;
  status: ZoneStatus;
};

export type ZonesResponse = { zones: Zone[] };

export type HealthResponse = {
  status: "ok";
  zones: number;
  sessions: number;
  simulated_through: string;
};

// ---------------------------------------------------------------------------
// Destinations, prediction, opening soon, recommend
// ---------------------------------------------------------------------------

export type Destination = {
  destination_id: string;
  name: string;
  lat: number;
  lng: number;
};

export type DestinationsResponse = { destinations: Destination[] };

export type Prediction = {
  zone_id: string;
  zone_name: string;
  time: string;
  hour_of_week: number;
  baseline_occupancy: number;
  event_boost: number;
  /** Null exactly when event_boost is 1.0. */
  event_name: string | null;
  predicted_occupancy: number;
  predicted_availability: number;
};

export type OpeningSoonResult = {
  zone_id: string;
  zone_name: string;
  facility_name: string;
  opening_soon: number;
  distance_m: number;
  walk_minutes: number;
};

export type OpeningSoonResponse = {
  near: { lat: number; lng: number };
  evaluated_at: string;
  window_minutes: number;
  results: OpeningSoonResult[];
};

export type EventWarning = {
  event_name: string;
  start_time: string;
};

export type Recommendation = {
  rank: number;
  zone_id: string;
  zone_name: string;
  facility_name: string;
  operator: string;
  pay_app: string[];
  note: string | null;
  /** 0 when no rule applies at arrival. */
  hourly_rate: number;
  /** Null when no rule or no limit applies at arrival. */
  time_limit_min: number | null;
  enforced: boolean;
  distance_m: number;
  walk_minutes: number;
  within_walk_limit: boolean;
  predicted_availability: number;
  price_score: number;
  walk_score: number;
  score: number;
  /** Present when the Event_Boost at arrival exceeds 1.0; otherwise null or absent. */
  event_warning?: EventWarning | null;
};

export type RecommendWeights = {
  availability: number;
  price: number;
  walk: number;
};

export type RecommendResponse = {
  destination: { destination_id: string; name: string };
  arrival: string;
  weights: RecommendWeights;
  max_walk_minutes: number;
  results: Recommendation[];
};

// ---------------------------------------------------------------------------
// Demo scenarios
// ---------------------------------------------------------------------------

export type ScenarioName = "game_day" | "family_weekend" | "reset";

export type SkippedReason = "already_full" | "not_enforced" | null;

export type ScenarioEvent = {
  event_id: string;
  name: string;
  start_time: string;
  expires_at: string;
};

export type ScenarioAffectedZone = {
  zone_id: string;
  zone_name: string;
  occupied_before: number;
  occupied_after: number;
  boost: number;
  skipped_reason: SkippedReason;
};

export type ScenarioResult = {
  scenario: ScenarioName;
  /** The live Event; null for reset, which creates none. */
  event: ScenarioEvent | null;
  affected: ScenarioAffectedZone[];
};

export type ActiveScenario = {
  scenario: Exclude<ScenarioName, "reset">;
  event_name: string;
  triggered_at: string;
  expires_at: string;
  minutes_remaining: number;
};

export type DemoStatus = { active: ActiveScenario | null };

// ---------------------------------------------------------------------------
// Explore (associative engine)
// ---------------------------------------------------------------------------

export type ValueState = "selected" | "possible" | "alternative" | "excluded" | "selected_excluded";

/** Field name → selected Field_Values. OR within a field, AND across fields. */
export type Selection = Record<string, string[]>;

export type ExploreModelField = { name: string; values: string[] };

export type ExploreModel = {
  fields: ExploreModelField[];
  row_count: number;
  history_days: number;
};

export type ExploreFieldValue = {
  value: string;
  state: ValueState;
  count: number;
};

export type ExploreField = {
  name: string;
  values: ExploreFieldValue[];
};

export type ExploreKpis = {
  sessions: number;
  /** Null when no rows match. */
  avg_stay_min: number | null;
  revenue: number | null;
  overstay_rate: number | null;
  avg_occupancy: number | null;
};

export type ExploreHeatmap = {
  /** "Monday" … "Sunday". */
  days: string[];
  /** 0 … 23. */
  hours: number[];
  /** cells[day][hour]: occupancy 0–1, or null when the slot has no rows. */
  cells: (number | null)[][];
};

export type ExploreCharts = {
  sessions_by_zone: { zone: string; sessions: number }[];
  stay_length: { bucket: string; sessions: number }[];
  turnover: { zone: string; sessions_per_space_per_day: number; avg_stay_min: number }[];
};

export type ExploreResult = {
  selection: Selection;
  fields: ExploreField[];
  kpis: ExploreKpis;
  heatmap: ExploreHeatmap;
  charts: ExploreCharts;
};

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export type ApiErrorCode = "missing_parameter" | "invalid_parameter" | "not_found" | "unknown_scenario";

/** Error body returned by the API. `error` is one of ApiErrorCode for contract errors. */
export type ApiErrorBody = {
  error: string;
  parameter?: string;
  message: string;
  allowed?: string[];
};

/** The API answered with a non-2xx status (or an unreadable body). */
export class ApiRequestError extends Error {
  readonly status: number;
  /** API error code, e.g. "invalid_parameter"; "http_error" when the body had none. */
  readonly error: string;
  readonly parameter?: string;
  readonly allowed?: string[];
  /** Request path, e.g. "/recommend". */
  readonly path: string;

  constructor(status: number, body: ApiErrorBody, path: string) {
    super(body.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.error = body.error;
    this.parameter = body.parameter;
    this.allowed = body.allowed;
    this.path = path;
  }
}

/** fetch itself failed (TypeError): the API isn't running or can't be reached. */
export class ApiUnreachableError extends Error {
  readonly apiBase: string;
  readonly path: string;

  constructor(path: string, cause?: unknown) {
    super(
      `Park LU can't reach its API at ${API_BASE}. Start it from the api folder with ` +
        `${API_START_COMMAND}, then select Try Again.`,
      { cause },
    );
    this.name = "ApiUnreachableError";
    this.apiBase = API_BASE;
    this.path = path;
  }
}

// ---------------------------------------------------------------------------
// Request helper
// ---------------------------------------------------------------------------

/** Per-call options. Pass a signal to cancel superseded requests. */
export type RequestOptions = { signal?: AbortSignal };

type Query = Record<string, string | number | undefined>;

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ""}`;
}

function isAbortError(err: unknown): boolean {
  return typeof err === "object" && err !== null && (err as { name?: unknown }).name === "AbortError";
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.error === "string" && typeof v.message === "string";
}

function fallbackMessage(status: number, path: string): string {
  if (status === 404) {
    return `The Park LU API has no route for ${path}. Restart the API with the current code, then select Try Again.`;
  }
  if (status >= 500) {
    return `The Park LU API hit an internal error (HTTP ${status}) on ${path}. Check the API terminal for details, then select Try Again.`;
  }
  return `The Park LU API rejected the request to ${path} (HTTP ${status}). Check the request, then select Try Again.`;
}

async function toRequestError(res: Response, path: string): Promise<ApiRequestError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // Not JSON; fall through to the generic message.
  }
  if (isApiErrorBody(body)) return new ApiRequestError(res.status, body, path);
  return new ApiRequestError(res.status, { error: "http_error", message: fallbackMessage(res.status, path) }, path);
}

async function request<T>(
  method: "GET" | "POST",
  path: string,
  { query, body, signal }: { query?: Query; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), {
      method,
      cache: "no-store",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (err instanceof TypeError) throw new ApiUnreachableError(path, err);
    throw err;
  }

  if (!res.ok) throw await toRequestError(res, path);

  try {
    return (await res.json()) as T;
  } catch (err) {
    if (isAbortError(err)) throw err;
    if (err instanceof TypeError) throw new ApiUnreachableError(path, err);
    throw new ApiRequestError(
      res.status,
      {
        error: "invalid_response",
        message: `The Park LU API sent a response from ${path} that isn't valid JSON. Restart the API, then select Try Again.`,
      },
      path,
    );
  }
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/** GET /health */
export function getHealth(opts: RequestOptions = {}): Promise<HealthResponse> {
  return request("GET", "/health", opts);
}

/** GET /zones: every zone with its rule now and its Zone_Status (Req 7.4, 15.1). */
export function getZones(opts: RequestOptions = {}): Promise<ZonesResponse> {
  return request("GET", "/zones", opts);
}

/** GET /destinations */
export function getDestinations(opts: RequestOptions = {}): Promise<DestinationsResponse> {
  return request("GET", "/destinations", opts);
}

/** GET /predict?zone=&time= (time is ISO 8601; naive times are read as America/New_York). */
export function getPredict(zoneId: string, timeIso: string, opts: RequestOptions = {}): Promise<Prediction> {
  return request("GET", "/predict", { query: { zone: zoneId, time: timeIso }, ...opts });
}

/** GET /opening-soon?near=lat,lng */
export function getOpeningSoon(lat: number, lng: number, opts: RequestOptions = {}): Promise<OpeningSoonResponse> {
  // Fixed-point keeps the value in the strict "lat,lng" decimal form the API parses.
  const near = `${lat.toFixed(6)},${lng.toFixed(6)}`;
  return request("GET", "/opening-soon", { query: { near }, ...opts });
}

/** GET /recommend?destination=&arrival=&limit= (limit 1–20, API default 5). */
export function getRecommend(
  destination: string,
  arrivalIso: string,
  limit?: number,
  opts: RequestOptions = {},
): Promise<RecommendResponse> {
  return request("GET", "/recommend", { query: { destination, arrival: arrivalIso, limit }, ...opts });
}

/** POST /demo/scenario */
export function postScenario(scenario: ScenarioName, opts: RequestOptions = {}): Promise<ScenarioResult> {
  return request("POST", "/demo/scenario", { body: { scenario }, ...opts });
}

/** GET /demo/status */
export function getDemoStatus(opts: RequestOptions = {}): Promise<DemoStatus> {
  return request("GET", "/demo/status", opts);
}

/** GET /explore/model */
export function getExploreModel(opts: RequestOptions = {}): Promise<ExploreModel> {
  return request("GET", "/explore/model", opts);
}

/** POST /explore/query */
export function postExploreQuery(selection: Selection, opts: RequestOptions = {}): Promise<ExploreResult> {
  return request("POST", "/explore/query", { body: { selection }, ...opts });
}

/** POST /explore/select: applies the click semantics and returns the resulting selection. */
export function postExploreSelect(
  selection: Selection,
  field: string,
  value: string,
  opts: RequestOptions = {},
): Promise<ExploreResult> {
  return request("POST", "/explore/select", { body: { selection, field, value }, ...opts });
}
