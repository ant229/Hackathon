"use client";

// Explore horizontal bar chart, hand-built from buttons (Req 12.8, no chart
// library). Bars use the neutral --text-2 fill so green, amber, and red keep
// their single meaning, availability (Req 17.7). Selected bars use the accent
// fill plus a check icon and aria-pressed, so the state never rests on color
// alone. Every bar shows its value as text and has an accessible name such as
// "Packer Ave Meters, 412 sessions" (Req 12.13). Bars start at zero and scale
// to the largest value (charts.md › Axes). Nothing animates (Req 17.8).
//
// Each bar is a full-width row: the label and value on top, the bar beneath, so
// long zone names never squeeze the plot area on narrow screens (charts.md ›
// Best practices: maximize the plot width in a compact environment).
import { useId, useState } from "react";
import { Icon } from "@/components/Icons";
import styles from "./Charts.module.css";

export type BarChartItem = {
  /** Category label, e.g. a zone name or a Stay Length bucket. Passed to onSelect. */
  label: string;
  /** Numeric value that sets the bar length. */
  value: number;
  /** Visible value text, e.g. "412" or "4.1". */
  valueText: string;
  /** Optional secondary text under the label, e.g. "Average stay 71 min". */
  detail?: string;
};

export type BarChartProps = {
  title: string;
  items: BarChartItem[];
  /** Unit read after the value, e.g. "sessions" or "sessions per space per day". */
  unitLabel: string;
  /** When set, bars are buttons; selecting one reports its label. */
  onSelect?: (label: string) => void;
  /** Labels of the bars that are part of the current selection. */
  selectedLabels?: string[];
  /** Show only the first N bars, with a Show All control for the rest. */
  maxItems?: number;
  /** Caption text under the title. Defaults to "Bar length shows <unitLabel>." */
  description?: string;
  /** Text shown when there are no items. */
  emptyText?: string;
  /** Heading level of the title within the page outline. Defaults to 3. */
  headingLevel?: 2 | 3 | 4;
  className?: string;
};

function barWidth(value: number, max: number): string {
  if (!(max > 0) || !Number.isFinite(value) || value <= 0) return "0";
  const pct = Math.min(100, (value / max) * 100);
  // A nonzero value always draws a visible sliver.
  return `max(2px, ${pct}%)`;
}

export function BarChart({
  title,
  items,
  unitLabel,
  onSelect,
  selectedLabels,
  maxItems,
  description,
  emptyText = "No data for these selections.",
  headingLevel = 3,
  className,
}: BarChartProps) {
  const titleId = useId();
  const descriptionId = useId();
  const listId = useId();
  const [expanded, setExpanded] = useState(false);
  const Heading = `h${headingLevel}` as "h2" | "h3" | "h4";

  const selectable = typeof onSelect === "function";
  const max = items.reduce((m, item) => (Number.isFinite(item.value) && item.value > m ? item.value : m), 0);
  const limit = maxItems !== undefined && maxItems > 0 ? Math.floor(maxItems) : items.length;
  const hasMore = items.length > limit;
  const visible = hasMore && !expanded ? items.slice(0, limit) : items;

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
          {description ?? `Bar length shows ${unitLabel}.`}
        </p>
      </figcaption>

      {items.length === 0 ? (
        <p className={styles.chartEmpty}>{emptyText}</p>
      ) : (
        <ul id={listId} className={styles.barList}>
          {visible.map((item) => {
            const selected = selectedLabels?.includes(item.label) ?? false;
            const content = (
              <>
                <span className={styles.barHead}>
                  <span className={styles.barLabel}>
                    <span className={styles.barName}>{item.label}</span>
                    {selected ? <Icon name="check" size={18} className={styles.barCheck} /> : null}
                  </span>
                  <span className={`${styles.barValue} tabular-nums`}>
                    {item.valueText}
                    {selectable ? null : <span className="visually-hidden"> {unitLabel}</span>}
                  </span>
                </span>
                {item.detail ? <span className={styles.barDetail}>{item.detail}</span> : null}
                <span className={styles.barTrack} aria-hidden="true">
                  <span className={styles.barFill} style={{ width: barWidth(item.value, max) }} />
                </span>
              </>
            );

            return (
              <li key={item.label}>
                {onSelect ? (
                  <button
                    type="button"
                    className={styles.bar}
                    data-selected={selected || undefined}
                    aria-pressed={selected}
                    aria-label={`${item.label}, ${item.valueText} ${unitLabel}${item.detail ? `, ${item.detail}` : ""}`}
                    onClick={() => onSelect(item.label)}
                  >
                    {content}
                  </button>
                ) : (
                  <div className={styles.bar} data-selected={selected || undefined}>
                    {content}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {hasMore ? (
        <button
          type="button"
          className={`button ${styles.barMore}`}
          aria-expanded={expanded}
          aria-controls={listId}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? "Show Fewer" : `Show All ${items.length}`}
        </button>
      ) : null}
    </figure>
  );
}

export default BarChart;
