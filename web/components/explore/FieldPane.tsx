"use client";

// One Explore filter pane: a field's values as buttons, each showing its
// Value_State as color plus an icon, the value, and its session count (Req 11.8).
// Each button's accessible name repeats the state, for example
// "Saturday, Selected, 2,210 sessions", and aria-pressed marks selected values.
//
// At compact widths (< 768 px) the pane collapses behind a disclosure button with
// aria-expanded inside an h3 (disclosure-controls.md › Disclosure triangles), so a
// phone shows the field list first and reveals values on demand. Fields with many
// short values, such as Arrival Hour, wrap as a grid of compact chips that stay at
// least 44 px tall. Values keep the order the API sends.
import { useId, useState, useSyncExternalStore } from "react";
import type { ExploreField, ExploreFieldValue, ValueState } from "../../lib/api";
import { formatHour, formatNumber } from "../../lib/format";
import { Icon } from "../Icons";
import { VALUE_STATE_META } from "./StateLegend";
import styles from "./Selection.module.css";

// ---------------------------------------------------------------------------
// Shared helpers (SelectionBar uses formatFieldValue too)
// ---------------------------------------------------------------------------

/** Display text for a Field_Value. Arrival Hour "14" reads "2 PM"; everything else is unchanged. */
export function formatFieldValue(field: string, value: string): string {
  if (field === "Arrival Hour" && /^\d{1,2}$/.test(value)) return formatHour(Number(value));
  return value;
}

/** True for the two states that are part of the Selection. */
export function isSelectedState(state: ValueState): boolean {
  return state === "selected" || state === "selected_excluded";
}

function sessionsText(count: number): string {
  return `${formatNumber(count)} ${count === 1 ? "session" : "sessions"}`;
}

/** Accessible name that repeats the state: "Saturday, Selected, 2,210 sessions". */
export function valueAccessibleName(field: string, value: ExploreFieldValue): string {
  return `${formatFieldValue(field, value.value)}, ${VALUE_STATE_META[value.state].label}, ${sessionsText(value.count)}`;
}

// ---------------------------------------------------------------------------
// Compact width (matches AppShell's 768 px breakpoint)
// ---------------------------------------------------------------------------

const COMPACT_QUERY = "(max-width: 767.98px)";

function subscribeCompact(onChange: () => void): () => void {
  const mql = window.matchMedia(COMPACT_QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

const getCompact = () => window.matchMedia(COMPACT_QUERY).matches;
const getCompactOnServer = () => false;

function useIsCompact(): boolean {
  return useSyncExternalStore(subscribeCompact, getCompact, getCompactOnServer);
}

// ---------------------------------------------------------------------------
// Layout choice
// ---------------------------------------------------------------------------

/** Many short values (Arrival Hour's 24) wrap as a chip grid; the rest are rows. */
const GRID_MIN_VALUES = 9;
const GRID_MAX_LABEL = 6;

type ValueLayout = "list" | "grid";

function chooseLayout(labels: string[]): ValueLayout {
  return labels.length >= GRID_MIN_VALUES && labels.every((label) => label.length <= GRID_MAX_LABEL)
    ? "grid"
    : "list";
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

export interface FieldPaneProps {
  /** The field with every value's state and count, from /explore/query or /explore/select. */
  field: ExploreField;
  /** Called with the field name and the raw Field_Value (not the display text). */
  onSelectValue: (field: string, value: string) => void;
  /**
   * true: always behind a disclosure. false: always open with a plain heading.
   * Omitted: a disclosure at compact widths only.
   */
  collapsible?: boolean;
  /** Whether a collapsible pane starts expanded. Default false. */
  defaultOpen?: boolean;
  /** Show at most this many values until Show All. Selected values always show. */
  maxVisible?: number;
  className?: string;
}

export function FieldPane({
  field,
  onSelectValue,
  collapsible,
  defaultOpen = false,
  maxVisible,
  className,
}: FieldPaneProps) {
  const isCompact = useIsCompact();
  const isCollapsible = collapsible ?? isCompact;
  const [open, setOpen] = useState(defaultOpen);
  const [showAll, setShowAll] = useState(false);

  const id = useId();
  const headingId = `${id}-heading`;
  const contentId = `${id}-content`;
  const listId = `${id}-list`;

  const { name, values } = field;
  const selectedCount = values.filter((v) => isSelectedState(v.state)).length;
  const summary =
    selectedCount > 0
      ? `${formatNumber(selectedCount)} Selected`
      : `${formatNumber(values.length)} ${values.length === 1 ? "Value" : "Values"}`;

  const layout = chooseLayout(values.map((v) => formatFieldValue(name, v.value)));

  const limit = maxVisible !== undefined && maxVisible > 0 && values.length > maxVisible ? maxVisible : null;
  const visible =
    limit !== null && !showAll
      ? values.filter((v, i) => i < limit || isSelectedState(v.state))
      : values;

  const expanded = !isCollapsible || open;

  const headingText = (
    <>
      <span className={styles.paneName}>{name}</span>
      <span className="visually-hidden">, </span>
      <span className={`${styles.paneSummary} tabular-nums`}>{summary}</span>
    </>
  );

  return (
    <div className={[styles.pane, className].filter(Boolean).join(" ")}>
      <h3 id={headingId} className={styles.paneHeading}>
        {isCollapsible ? (
          <button
            type="button"
            className={styles.disclosure}
            aria-expanded={open}
            aria-controls={contentId}
            onClick={() => setOpen((value) => !value)}
          >
            <Icon
              name={open ? "chevron-down" : "chevron-right"}
              size={20}
              className={styles.disclosureIcon}
            />
            {headingText}
          </button>
        ) : (
          <span className={styles.paneHeadingStatic}>{headingText}</span>
        )}
      </h3>

      <div id={contentId} className={styles.paneContent} hidden={!expanded}>
        {values.length === 0 ? (
          <p className={styles.paneEmpty}>This field has no values yet.</p>
        ) : (
          <ul
            id={listId}
            role="list"
            aria-labelledby={headingId}
            className={layout === "grid" ? styles.valueGrid : styles.valueList}
          >
            {visible.map((value) => (
              <li key={value.value} className={styles.valueItem}>
                <ValueButton field={name} value={value} layout={layout} onSelectValue={onSelectValue} />
              </li>
            ))}
          </ul>
        )}

        {limit !== null ? (
          <button
            type="button"
            className={`button ${styles.showMore}`}
            aria-expanded={showAll}
            aria-controls={listId}
            onClick={() => setShowAll((value) => !value)}
          >
            {showAll ? "Show Fewer" : `Show All ${formatNumber(values.length)}`}
          </button>
        ) : null}
      </div>
    </div>
  );
}

interface ValueButtonProps {
  field: string;
  value: ExploreFieldValue;
  layout: ValueLayout;
  onSelectValue: (field: string, value: string) => void;
}

function ValueButton({ field, value, layout, onSelectValue }: ValueButtonProps) {
  const meta = VALUE_STATE_META[value.state];
  const label = formatFieldValue(field, value.value);

  return (
    <button
      type="button"
      className={[styles.value, layout === "grid" ? styles.valueChip : styles.valueRow, meta.className].join(" ")}
      aria-pressed={isSelectedState(value.state)}
      aria-label={valueAccessibleName(field, value)}
      data-state={value.state}
      onClick={() => onSelectValue(field, value.value)}
    >
      <Icon name={meta.icon} size={layout === "grid" ? 16 : 20} className={styles.valueIcon} />
      <span className={styles.valueLabel}>{label}</span>
      <span className={`${styles.valueCount} tabular-nums`}>{formatNumber(value.count)}</span>
    </button>
  );
}
