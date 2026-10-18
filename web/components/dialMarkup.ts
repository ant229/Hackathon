// Availability Dial geometry and the HTML-string renderer for Leaflet divIcons.
//
// No "use client": everything here except updateDialElement is pure, so server
// components, the React <Dial>, and the map can all share one geometry. Both
// renderers draw the same three circles from DIAL_GEOMETRY:
//
//   disc  r = 22    --surface backing, so the dial reads on any map tile
//   track r = 18    band color tinted 25 % into --surface (--separator fallback)
//   arc   r = 18    band color, filled clockwise from 12 o'clock in proportion
//                   to percent free (Req 7.2, 7.3)
//
// Pin styles live in ./dialPin.css, a global stylesheet whose classes all start
// with "ss-dial". ZoneMap must import it once: `import "../dialPin.css";`
import { availabilityBand, percentFree, type AvailabilityBand } from "../lib/format";

// ---------------------------------------------------------------------------
// Geometry (SVG user units on a 44 x 44 viewBox)
// ---------------------------------------------------------------------------

const VIEWBOX = 44;
const STROKE = 5;
/** Surface rim between the ring's outer edge and the disc edge. */
const RIM = 1.5;
const RADIUS = VIEWBOX / 2 - RIM - STROKE / 2; // 18

export const DIAL_GEOMETRY = {
  viewBox: VIEWBOX,
  center: VIEWBOX / 2,
  discRadius: VIEWBOX / 2,
  radius: RADIUS,
  stroke: STROKE,
  circumference: 2 * Math.PI * RADIUS,
  /** stroke-dasharray: the circumference rounded to 3 decimals. */
  dashArray: Math.round(2 * Math.PI * RADIUS * 1000) / 1000,
  /** Starts the arc at 12 o'clock and fills clockwise. */
  arcTransform: `rotate(-90 ${VIEWBOX / 2} ${VIEWBOX / 2})`,
} as const;

/** Rendered ring diameter in CSS pixels for each <Dial> size. */
export const DIAL_SIZES = { sm: 44, lg: 72 } as const;

/**
 * Leaflet divIcon metrics for renderDialHtml: a 44 px ring over a 20 px capsule,
 * 76 px wide so "100% free" fits. The anchor is the ring center, so the dial sits
 * on the facility coordinates. Use these for `iconSize`, `iconAnchor`, and
 * `className` (which also replaces Leaflet's white default icon box).
 */
export const DIAL_PIN: {
  className: string;
  width: number;
  height: number;
  iconSize: [number, number];
  iconAnchor: [number, number];
} = {
  className: "ss-dial-icon",
  width: 76,
  height: 66,
  iconSize: [76, 66],
  iconAnchor: [38, DIAL_SIZES.sm / 2],
};

// ---------------------------------------------------------------------------
// Readings
// ---------------------------------------------------------------------------

/** A dial value: Zone_Status `occupied` (0–1) or an already computed percent free (0–100). */
export type DialValue =
  | { occupied: number; percentFree?: never }
  | { percentFree: number; occupied?: never };

export interface DialReading {
  /** Whole percent free, 0–100. */
  percent: number;
  band: AvailabilityBand;
  /** stroke-dashoffset for the arc: circumference × (1 − percent / 100). */
  dashOffset: number;
  /** Capsule text, e.g. "62% free". */
  capsuleText: string;
}

const round3 = (n: number) => Math.round(n * 1000) / 1000;

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}

/** Percent free, band, arc offset, and capsule text for a dial value. */
export function readDial(value: DialValue): DialReading {
  const percent =
    typeof value.percentFree === "number"
      ? clampPercent(value.percentFree)
      : percentFree(value.occupied ?? Number.NaN);
  return {
    percent,
    band: availabilityBand(percent),
    dashOffset: round3(DIAL_GEOMETRY.circumference * (1 - percent / 100)),
    capsuleText: `${percent}% free`,
  };
}

/**
 * Accessible name that carries the band as text, not color alone (Req 7.12, 17.7):
 * "62% free, Plenty Free", or "E 3rd St RapidPark West, 12% free, Nearly Full" with a label.
 */
export function dialAccessibleName(value: DialValue, label?: string): string {
  const { capsuleText, band } = readDial(value);
  const prefix = label?.trim() ? `${label.trim()}, ` : "";
  return `${prefix}${capsuleText}, ${band.label}`;
}

// ---------------------------------------------------------------------------
// HTML string for Leaflet divIcon
// ---------------------------------------------------------------------------

export type DialPinInput = DialValue & {
  /** Zone name, prefixed to the visually hidden accessible text. */
  label?: string;
  /** Selected zone: accent halo around the ring and an accent capsule. */
  selected?: boolean;
};

const HTML_ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/** Escapes text for HTML content and attribute values. */
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}

/**
 * The Availability Dial as an HTML string for `L.divIcon({ html })`. Same geometry
 * as <Dial size="sm">. The SVG and capsule are hidden from assistive technology;
 * a visually hidden span carries the full name, so a marker without its own
 * aria-label still reads "Zone, 62% free, Plenty Free". All text is escaped.
 */
export function renderDialHtml(input: DialPinInput): string {
  const g = DIAL_GEOMETRY;
  const reading = readDial(input);
  const name = escapeHtml(dialAccessibleName(input, input.label));
  const classes = input.selected ? "ss-dial ss-dial-selected" : "ss-dial";
  const size = DIAL_SIZES.sm;
  const c = g.center;

  return (
    `<div class="${classes}" data-band="${reading.band.band}" data-percent="${reading.percent}"` +
    ` style="width:${DIAL_PIN.width}px;height:${DIAL_PIN.height}px">` +
    `<svg class="ss-dial-ring" width="${size}" height="${size}" viewBox="0 0 ${g.viewBox} ${g.viewBox}"` +
    ` aria-hidden="true" focusable="false">` +
    `<circle class="ss-dial-disc" cx="${c}" cy="${c}" r="${g.discRadius}"/>` +
    `<circle class="ss-dial-track" cx="${c}" cy="${c}" r="${g.radius}" fill="none" stroke-width="${g.stroke}"/>` +
    `<circle class="ss-dial-arc" cx="${c}" cy="${c}" r="${g.radius}" fill="none" stroke-width="${g.stroke}"` +
    ` stroke-dasharray="${g.dashArray}" transform="${g.arcTransform}"` +
    ` style="stroke-dashoffset:${reading.dashOffset}"/>` +
    `</svg>` +
    `<span class="ss-dial-capsule" aria-hidden="true">${reading.capsuleText}</span>` +
    `<span class="ss-dial-sr">${name}</span>` +
    `</div>`
  );
}

/**
 * Updates a dial rendered by renderDialHtml in place, so the 300 ms arc transition
 * plays instead of the icon being replaced (Leaflet's setIcon rewrites innerHTML).
 * Pass the marker's icon element or the `.ss-dial` element itself. Returns false
 * when the markup isn't found; fall back to `marker.setIcon(...)` then.
 */
export function updateDialElement(element: Element, input: DialPinInput): boolean {
  const root = element.classList.contains("ss-dial") ? element : element.querySelector(".ss-dial");
  if (!root) return false;
  const arc = root.querySelector<SVGCircleElement>(".ss-dial-arc");
  const capsule = root.querySelector(".ss-dial-capsule");
  const sr = root.querySelector(".ss-dial-sr");
  if (!arc || !capsule || !sr) return false;

  const reading = readDial(input);
  root.setAttribute("data-band", reading.band.band);
  root.setAttribute("data-percent", String(reading.percent));
  root.classList.toggle("ss-dial-selected", Boolean(input.selected));
  arc.style.strokeDashoffset = String(reading.dashOffset);
  capsule.textContent = reading.capsuleText;
  sr.textContent = dialAccessibleName(input, input.label);
  return true;
}
