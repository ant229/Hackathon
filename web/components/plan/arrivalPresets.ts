// Quick arrival times for Plan a Visit. Every preset is computed on Bethlehem's
// wall clock (America/New_York), so "Tonight 7 PM" means 7 PM in Bethlehem no
// matter where the browser is. Values are `datetime-local` strings
// ("YYYY-MM-DDTHH:mm"), which toIsoWithOffset turns into ISO with the offset.
import { toBethlehemLocalInput } from "@/lib/format";

export type ArrivalPresetId = "now" | "in1h" | "tonight" | "saturday";

/** Chip order and title-style labels (Req 17.14). */
export const ARRIVAL_PRESETS: readonly { id: ArrivalPresetId; label: string }[] = [
  { id: "now", label: "Now" },
  { id: "in1h", label: "In 1 Hour" },
  { id: "tonight", label: "Tonight 7 PM" },
  { id: "saturday", label: "Saturday 12 PM" },
];

/** The preset selected when Plan a Visit opens. */
export const DEFAULT_ARRIVAL_PRESET: ArrivalPresetId = "in1h";

const HOUR_MS = 60 * 60 * 1000;

const pad = (n: number, width = 2) => String(n).padStart(width, "0");

/** The calendar date `days` after year-month-day, as "YYYY-MM-DD". Pure date math, no time zone. */
function shiftDate(year: number, month: number, day: number, days: number): string {
  const d = new Date(Date.UTC(year, month - 1, day + days));
  return `${pad(d.getUTCFullYear(), 4)}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

/**
 * The `datetime-local` value for a preset at the instant `now`:
 * - Now: the current Bethlehem time.
 * - In 1 Hour: Bethlehem time one hour from now (DST-safe: it adds an hour to the instant).
 * - Tonight 7 PM: today at 19:00; once 7 PM has passed, tomorrow at 19:00.
 * - Saturday 12 PM: the next Saturday at 12:00, or today when it's Saturday before noon.
 */
export function arrivalPresetValue(id: ArrivalPresetId, now: Date): string {
  switch (id) {
    case "now":
      return toBethlehemLocalInput(now);
    case "in1h":
      return toBethlehemLocalInput(new Date(now.getTime() + HOUR_MS));
    case "tonight":
    case "saturday": {
      const local = toBethlehemLocalInput(now); // "YYYY-MM-DDTHH:mm"
      const year = Number(local.slice(0, 4));
      const month = Number(local.slice(5, 7));
      const day = Number(local.slice(8, 10));
      const hour = Number(local.slice(11, 13));

      if (id === "tonight") {
        return `${shiftDate(year, month, day, hour >= 19 ? 1 : 0)}T19:00`;
      }

      // 0 = Sunday … 6 = Saturday, for the Bethlehem calendar date.
      const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
      let days = (6 - weekday + 7) % 7;
      if (days === 0 && hour >= 12) days = 7;
      return `${shiftDate(year, month, day, days)}T12:00`;
    }
  }
}

/** Default arrival value, In 1 Hour from the current instant. */
export function defaultArrivalValue(): string {
  return arrivalPresetValue(DEFAULT_ARRIVAL_PRESET, new Date());
}
