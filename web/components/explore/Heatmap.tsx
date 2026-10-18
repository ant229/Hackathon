"use client";

// Explore occupancy heatmap: 7 day rows by 24 arrival-hour columns (Req 12.7).
// Each cell is a 44 px button (Req 17.4). Its fill uses the map's availability
// bands applied to 1 − occupancy, so green, amber, and red keep one meaning
// across the app, and the cell shows its occupancy as text so color is never the
// only signal (Req 17.7). Accessible names read "Saturday 2 PM, 81% occupied"
// (Req 12.13). Selecting a cell reports its day and hour; ExploreView turns that
// into Day and Arrival Hour selections (Req 12.10).
//
// Keyboard: the grid is one tab stop with a roving tabindex. Arrow keys move
// between cells, Home and End jump to the first and last hour of the row, and
// Ctrl or Cmd with Home or End jumps to the first or last cell (charts.md ›
// Best practices: let people move focus among values without visiting every
// one in sequence). The scroll region is focusable too, so keyboard users can
// scroll it on narrow screens.
import { useId, useRef, useState, type KeyboardEvent } from "react";
import type { ExploreHeatmap } from "@/lib/api";
import { availabilityBand, formatHour, percentFree, type AvailabilityBandName } from "@/lib/format";
import styles from "./Charts.module.css";

export type HeatmapProps = {
  heatmap: ExploreHeatmap;
  /** Called with the cell's day ("Saturday") and hour (0–23). */
  onSelect: (day: string, hour: number) => void;
  /** Selected Day values. A cell is selected when its day and hour are both selected. */
  selectedDay?: string[];
  /** Selected Arrival Hour values as numbers (0–23). */
  selectedHours?: number[];
  /** Visible title. Defaults to "Occupancy by Day and Hour". */
  title?: string;
  /** Heading level of the title within the page outline. Defaults to 3. */
  headingLevel?: 2 | 3 | 4;
  className?: string;
};

type Cell = {
  /** Rounded percent occupied, or null when the slot has no sessions. */
  occupiedPct: number | null;
  band: AvailabilityBandName | null;
  name: string;
};

/** The highest-occupancy slot: day index, hour index, and percent occupied. */
type Busiest = { d: number; h: number; pct: number };

function readCell(day: string, hour: number, occupancy: number | null | undefined): Cell {
  const when = `${day} ${formatHour(hour)}`;
  if (occupancy === null || occupancy === undefined || !Number.isFinite(occupancy)) {
    return { occupiedPct: null, band: null, name: `${when}, No sessions` };
  }
  // Derive the shown number from percent free so the number and the band always agree.
  const free = percentFree(occupancy);
  const occupiedPct = 100 - free;
  return { occupiedPct, band: availabilityBand(free).band, name: `${when}, ${occupiedPct}% occupied` };
}

// The same bands as the map dials, stated in occupancy terms because the cells
// show percent occupied: free ≥ 40 ⇔ occupied ≤ 60; free 15–39 ⇔ occupied 61–85.
const LEGEND: { band: AvailabilityBandName; label: string; meaning: string }[] = [
  { band: "free", label: availabilityBand(100).label, meaning: "60% or less occupied" },
  { band: "tight", label: availabilityBand(39).label, meaning: "61–85% occupied" },
  { band: "full", label: availabilityBand(0).label, meaning: "86% or more occupied" },
];

export function Heatmap({
  heatmap,
  onSelect,
  selectedDay,
  selectedHours,
  title = "Occupancy by Day and Hour",
  headingLevel = 3,
  className,
}: HeatmapProps) {
  const { days, hours, cells } = heatmap;
  const rows = days.length;
  const cols = hours.length;

  const titleId = useId();
  const descriptionId = useId();
  const Heading = `h${headingLevel}` as "h2" | "h3" | "h4";

  const grid: Cell[][] = days.map((day, d) => hours.map((hour, h) => readCell(day, hour, cells[d]?.[h])));

  const isSelected = (d: number, h: number) =>
    Boolean(selectedDay?.includes(days[d]) && selectedHours?.includes(hours[h]));

  // Busiest slot, as a one-line headline (charting-data.md › Aid comprehension).
  let busiest: Busiest | null = null;
  let firstSelected: number | null = null;
  for (let d = 0; d < rows; d++) {
    for (let h = 0; h < cols; h++) {
      const pct = grid[d][h].occupiedPct;
      if (pct !== null && (busiest === null || pct > busiest.pct)) busiest = { d, h, pct };
      if (firstSelected === null && isSelected(d, h)) firstSelected = d * cols + h;
    }
  }
  const summary = summaryText(busiest, days, hours);

  // Roving tabindex: the active cell is the one last focused, else the first
  // selected cell, else the first cell.
  const [active, setActive] = useState<number | null>(null);
  const cellRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const total = rows * cols;
  const tabStop = active !== null && active < total ? active : (firstSelected ?? 0);

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, d: number, h: number) {
    let nextD = d;
    let nextH = h;
    const jump = event.ctrlKey || event.metaKey;
    switch (event.key) {
      case "ArrowRight":
        nextH = Math.min(cols - 1, h + 1);
        break;
      case "ArrowLeft":
        nextH = Math.max(0, h - 1);
        break;
      case "ArrowDown":
        nextD = Math.min(rows - 1, d + 1);
        break;
      case "ArrowUp":
        nextD = Math.max(0, d - 1);
        break;
      case "Home":
        nextH = 0;
        if (jump) nextD = 0;
        break;
      case "End":
        nextH = cols - 1;
        if (jump) nextD = rows - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    const index = nextD * cols + nextH;
    setActive(index);
    cellRefs.current[index]?.focus();
  }

  return (
    <figure
      className={[styles.figure, className].filter(Boolean).join(" ")}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
    >
      <figcaption className={styles.caption}>
        <Heading id={titleId} className={styles.chartTitle}>
          {title}
        </Heading>
        <p id={descriptionId} className={styles.chartDescription}>
          Average occupancy of the selected zones by day and arrival hour. Each number is the percent of
          spaces occupied. Select a cell to filter to that day and hour; with a keyboard, use the arrow keys to
          move between cells.
        </p>
        <p className={`${styles.chartSummary} tabular-nums`}>{summary}</p>
      </figcaption>

      <ul className={styles.legend} aria-label="Heatmap color key">
        {LEGEND.map((entry) => (
          <li key={entry.band} className={styles.legendItem}>
            <span className={styles.swatch} data-band={entry.band} aria-hidden="true" />
            <span>
              <span className={styles.legendLabel}>{entry.label}</span>{" "}
              <span className={styles.legendMeaning}>{entry.meaning}</span>
            </span>
          </li>
        ))}
        <li className={styles.legendItem}>
          <span className={styles.swatch} data-band="none" aria-hidden="true" />
          <span>
            <span className={styles.legendLabel}>No Sessions</span>{" "}
            <span className={styles.legendMeaning}>
              shown as <span aria-hidden="true">—</span>
              <span className="visually-hidden">a dash</span>
            </span>
          </span>
        </li>
      </ul>

      <div className={styles.hmScroll} role="region" aria-label={`${title}, cells`} tabIndex={0}>
        <div className={styles.hmGrid}>
          {/* Visible hour axis; cell names already carry every hour (charts.md › hide axis labels). */}
          <div className={styles.hmHeader} aria-hidden="true">
            <span className={styles.hmCorner} />
            {hours.map((hour) => (
              <span key={hour} className={styles.hmHour}>
                {hour % 3 === 0 ? formatHour(hour) : ""}
              </span>
            ))}
          </div>

          {days.map((day, d) => (
            <div key={day} role="group" aria-label={day} className={styles.hmRow}>
              <span className={styles.hmDay} aria-hidden="true">
                {day.slice(0, 3)}
              </span>
              {hours.map((hour, h) => {
                const cell = grid[d][h];
                const index = d * cols + h;
                return (
                  <button
                    key={hour}
                    ref={(el) => {
                      cellRefs.current[index] = el;
                    }}
                    type="button"
                    className={`${styles.hmCell} tabular-nums`}
                    data-band={cell.band ?? "none"}
                    aria-label={cell.name}
                    aria-pressed={isSelected(d, h)}
                    tabIndex={index === tabStop ? 0 : -1}
                    onFocus={() => setActive(index)}
                    onKeyDown={(event) => handleKeyDown(event, d, h)}
                    onClick={() => onSelect(day, hour)}
                  >
                    {cell.occupiedPct === null ? "—" : cell.occupiedPct}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </figure>
  );
}

function summaryText(busiest: Busiest | null, days: string[], hours: number[]): string {
  if (busiest === null) return "No sessions for these selections.";
  return `Busiest: ${days[busiest.d]} ${formatHour(hours[busiest.h])}, ${busiest.pct}% occupied.`;
}

export default Heatmap;
