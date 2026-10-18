// Display formatters shared by every Park LU screen.
// All clock times are shown in Bethlehem local time (America/New_York), on the
// server and in the browser alike, so server and client renders always match.

/** The documented command that starts the Analytics_API from the api folder (Req 17.16). */
export const API_START_COMMAND = "uv run uvicorn app.main:create_app --factory --port 8000";

/** Park LU's display time zone. */
export const BETHLEHEM_TZ = "America/New_York";

// ---------------------------------------------------------------------------
// Availability
// ---------------------------------------------------------------------------

/** Percent free = round((1 − occupied) × 100), clamped to 0–100 (Req 7.2). */
export function percentFree(occupied: number): number {
  if (!Number.isFinite(occupied)) return 0;
  const value = Math.round((1 - occupied) * 100);
  return Math.min(100, Math.max(0, value));
}

export type AvailabilityBandName = "free" | "tight" | "full";

export type AvailabilityBand = {
  band: AvailabilityBandName;
  /** Text label so color is never the only signal (Req 17.7). */
  label: "Plenty Free" | "Filling Up" | "Nearly Full";
  /** CSS custom property holding the band color. */
  cssVar: "--free" | "--tight" | "--full";
};

/** Band thresholds: free ≥ 40, tight 15–39, full < 15 (Req 7.3). */
export function availabilityBand(percentFreeValue: number): AvailabilityBand {
  if (percentFreeValue >= 40) return { band: "free", label: "Plenty Free", cssVar: "--free" };
  if (percentFreeValue >= 15) return { band: "tight", label: "Filling Up", cssVar: "--tight" };
  return { band: "full", label: "Nearly Full", cssVar: "--full" };
}

// ---------------------------------------------------------------------------
// Numbers, money, durations
// ---------------------------------------------------------------------------

const currencyFormat = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** "$2.50", "$3,810.25". */
export function formatCurrency(amount: number): string {
  return currencyFormat.format(amount);
}

/** "$2.50/hr". */
export function formatHourlyRate(rate: number): string {
  return `${formatCurrency(rate)}/hr`;
}

/** "2 H Limit", "3 H Limit", "90 Min Limit", or "No Time Limit". */
export function formatTimeLimit(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "No Time Limit";
  if (minutes % 60 === 0) return `${minutes / 60} H Limit`;
  return `${Math.round(minutes)} Min Limit`;
}

/** "45 min", "1 h 36 min", "2 h". */
export function formatMinutes(minutes: number): string {
  const total = Math.max(0, Math.round(minutes));
  if (total < 60) return `${total} min`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

const percentFormats = new Map<number, Intl.NumberFormat>();

/** Ratio (0–1) as a percent: formatPercent(0.118) → "12%", formatPercent(0.118, 1) → "11.8%". */
export function formatPercent(ratio: number, fractionDigits = 0): string {
  let fmt = percentFormats.get(fractionDigits);
  if (!fmt) {
    fmt = new Intl.NumberFormat("en-US", {
      style: "percent",
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    });
    percentFormats.set(fractionDigits, fmt);
  }
  return fmt.format(ratio);
}

const numberFormats = new Map<number, Intl.NumberFormat>();

/** Grouped number: formatNumber(2210) → "2,210", formatNumber(4.06, 1) → "4.1". */
export function formatNumber(value: number, maxFractionDigits = 0): string {
  let fmt = numberFormats.get(maxFractionDigits);
  if (!fmt) {
    fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: maxFractionDigits });
    numberFormats.set(maxFractionDigits, fmt);
  }
  return fmt.format(value);
}

// ---------------------------------------------------------------------------
// Bethlehem local time
// ---------------------------------------------------------------------------

const timeFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: BETHLEHEM_TZ,
  hour: "numeric",
  minute: "2-digit",
});

const dateTimeFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: BETHLEHEM_TZ,
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

function toDate(value: string | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "2:05 PM" in Bethlehem time. Returns "—" for an unparseable value. */
export function formatLocalTime(value: string | Date): string {
  const date = toDate(value);
  return date ? timeFormat.format(date) : "—";
}

/** "Sat, Nov 7, 7:30 PM" in Bethlehem time. Returns "—" for an unparseable value. */
export function formatLocalDateTime(value: string | Date): string {
  const date = toDate(value);
  return date ? dateTimeFormat.format(date) : "—";
}

/** Hour of day as a label: 0 → "12 AM", 14 → "2 PM". */
export function formatHour(hour: number): string {
  const h = ((Math.trunc(hour) % 24) + 24) % 24;
  const suffix = h < 12 ? "AM" : "PM";
  const twelve = h % 12 === 0 ? 12 : h % 12;
  return `${twelve} ${suffix}`;
}

// --- datetime-local <-> ISO with the America/New_York offset ---------------

type WallParts = { year: number; month: number; day: number; hour: number; minute: number; second: number };

const partsFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: BETHLEHEM_TZ,
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

/** Bethlehem wall-clock parts of an instant. */
function wallParts(epochMs: number): WallParts {
  const out: Record<string, number> = {};
  for (const part of partsFormat.formatToParts(new Date(epochMs))) {
    if (part.type !== "literal") out[part.type] = Number(part.value);
  }
  return {
    year: out.year,
    month: out.month,
    day: out.day,
    // Some engines report midnight as "24" even with h23; normalize it.
    hour: out.hour % 24,
    minute: out.minute,
    second: out.second,
  };
}

/** Bethlehem UTC offset in minutes (−300 for EST, −240 for EDT) at an instant. */
function offsetMinutes(epochMs: number): number {
  const whole = Math.floor(epochMs / 1000) * 1000;
  const p = wallParts(whole);
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  return Math.round((asUtc - whole) / 60_000);
}

const pad = (n: number, width = 2) => String(n).padStart(width, "0");

function formatOffset(minutes: number): string {
  const sign = minutes < 0 ? "-" : "+";
  const abs = Math.abs(minutes);
  return `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

const LOCAL_INPUT = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$/;

/**
 * Converts a `datetime-local` value ("YYYY-MM-DDTHH:mm" or with seconds), read as
 * Bethlehem local time, to ISO 8601 with the correct offset, e.g.
 * "2026-07-04T19:00" → "2026-07-04T19:00:00-04:00" and
 * "2026-11-07T12:00" → "2026-11-07T12:00:00-05:00".
 *
 * DST is resolved with Intl only. A time that falls in the spring-forward gap moves
 * forward by the gap (02:30 → 03:30 EDT); an ambiguous fall-back time resolves to the
 * earlier instant (EDT). Returns null when the value isn't a valid local date-time.
 */
export function toIsoWithOffset(localValue: string): string | null {
  const m = LOCAL_INPUT.exec(localValue.trim());
  if (!m) return null;
  const [year, month, day, hour, minute] = m.slice(1, 6).map(Number);
  const second = m[6] ? Number(m[6]) : 0;
  if (month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) return null;

  // The wall time as if it were UTC; real instant = wall − offset.
  const wallAsUtc = Date.UTC(year, month - 1, day, hour, minute, second);
  const check = new Date(wallAsUtc);
  if (check.getUTCFullYear() !== year || check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day) {
    return null; // e.g. Feb 30
  }

  const o1 = offsetMinutes(wallAsUtc);
  let instant = wallAsUtc - o1 * 60_000;
  const o2 = offsetMinutes(instant);
  if (o2 !== o1) {
    const retry = wallAsUtc - o2 * 60_000;
    if (offsetMinutes(retry) === o2) {
      instant = retry;
    } else {
      // Nonexistent wall time (spring-forward gap): read it with the pre-transition offset.
      instant = wallAsUtc - Math.min(o1, o2) * 60_000;
    }
  }

  const p = wallParts(instant);
  const offset = offsetMinutes(instant);
  return (
    `${pad(p.year, 4)}-${pad(p.month)}-${pad(p.day)}` +
    `T${pad(p.hour)}:${pad(p.minute)}:${pad(p.second)}${formatOffset(offset)}`
  );
}

/** An instant as a `datetime-local` value ("YYYY-MM-DDTHH:mm") in Bethlehem time. */
export function toBethlehemLocalInput(date: Date): string {
  const p = wallParts(date.getTime());
  return `${pad(p.year, 4)}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`;
}

/** The current Bethlehem time as a `datetime-local` value, for default input values. */
export function nowInBethlehemLocalInput(): string {
  return toBethlehemLocalInput(new Date());
}
