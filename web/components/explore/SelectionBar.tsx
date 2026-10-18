"use client";

// Explore's Selection_Bar (Req 11.13–11.20): Back, Forward, Clear All, and one
// removable chip per field with a Selection, such as "Day: Saturday".
//
// Keyboard: role="toolbar" with one Tab stop and a roving tabindex. Left and Right
// arrows move between controls, Home and End jump to the ends. Back, Forward, and
// Clear All use aria-disabled at their ends instead of the disabled attribute, so
// they keep focus when they become unavailable (focus-and-selection.md › Best
// practices). When a chip is cleared from the keyboard, focus moves to the next chip,
// the previous chip, or Back, so it never drops to the page.
//
// At compact widths the bar sticks to the top of the page, and the chips scroll
// sideways so the bar stays two rows tall.
import { useId, useRef, useState, type FocusEvent, type KeyboardEvent, type MouseEvent } from "react";
import type { Selection } from "../../lib/api";
import { normalizeSelection } from "../../lib/selectionHistory";
import { Icon } from "../Icons";
import { formatFieldValue } from "./FieldPane";
import styles from "./Selection.module.css";

export interface SelectionBarProps {
  /** The current Selection. Chips follow its field order, which is the order people chose them. */
  selection: Selection;
  /** False at the first history entry: Back shows as disabled (Req 11.19). */
  canBack: boolean;
  /** False at the last history entry: Forward shows as disabled (Req 11.20). */
  canForward: boolean;
  onBack: () => void;
  onForward: () => void;
  onClearAll: () => void;
  /** Clears one field and leaves the others (Req 11.14). */
  onClearField: (field: string) => void;
  className?: string;
}

/** Values shown in a chip before it summarizes the rest as "+N more". */
const CHIP_VALUES_SHOWN = 2;

const BACK = "back";
const FORWARD = "forward";
const CLEAR_ALL = "clear-all";
const chipKey = (field: string) => `chip:${field}`;

type ToolbarItem = { key: string; enabled: boolean };

function shortValues(labels: string[]): string {
  if (labels.length <= CHIP_VALUES_SHOWN) return labels.join(", ");
  return `${labels.slice(0, CHIP_VALUES_SHOWN).join(", ")} +${labels.length - CHIP_VALUES_SHOWN} more`;
}

export function SelectionBar({
  selection,
  canBack,
  canForward,
  onBack,
  onForward,
  onClearAll,
  onClearField,
  className,
}: SelectionBarProps) {
  const id = useId();
  const toolbarRef = useRef<HTMLDivElement>(null);
  const [activeKey, setActiveKey] = useState(BACK);

  const chips = Object.entries(normalizeSelection(selection)).map(([field, values]) => {
    const labels = values.map((value) => formatFieldValue(field, value));
    return {
      field,
      short: shortValues(labels),
      full: `${field}: ${labels.join(", ")}`,
    };
  });
  const hasSelection = chips.length > 0;

  // Roving tabindex: the last focused control keeps the Tab stop while it exists
  // and is available; otherwise the first available control takes it.
  const items: ToolbarItem[] = [
    { key: BACK, enabled: canBack },
    { key: FORWARD, enabled: canForward },
    { key: CLEAR_ALL, enabled: hasSelection },
    ...chips.map((chip) => ({ key: chipKey(chip.field), enabled: true })),
  ];
  const tabStop = (
    items.find((item) => item.key === activeKey && item.enabled) ??
    items.find((item) => item.enabled) ??
    items[0]
  ).key;
  const tabIndexFor = (key: string) => (key === tabStop ? 0 : -1);

  function toolbarControls(): HTMLElement[] {
    const root = toolbarRef.current;
    return root ? Array.from(root.querySelectorAll<HTMLElement>("[data-toolbar-key]")) : [];
  }

  function focusKey(key: string) {
    toolbarControls()
      .find((el) => el.dataset.toolbarKey === key)
      ?.focus();
  }

  function handleFocus(event: FocusEvent<HTMLDivElement>) {
    const key = (event.target as HTMLElement).dataset?.toolbarKey;
    if (key) setActiveKey(key);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const controls = toolbarControls();
    const index = controls.indexOf(document.activeElement as HTMLElement);
    if (index === -1) return;

    let next: number;
    switch (event.key) {
      case "ArrowRight":
        next = (index + 1) % controls.length;
        break;
      case "ArrowLeft":
        next = (index - 1 + controls.length) % controls.length;
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = controls.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    controls[next].focus();
  }

  function handleClearField(event: MouseEvent<HTMLButtonElement>, field: string, index: number) {
    // Only move focus that is already here (keyboard, or a click that focused the
    // button); never pull focus in from elsewhere.
    if (document.activeElement === event.currentTarget) {
      const neighbor = chips[index + 1] ?? chips[index - 1];
      focusKey(neighbor ? chipKey(neighbor.field) : BACK);
    }
    onClearField(field);
  }

  const announcement = hasSelection
    ? `Selections: ${chips.map((chip) => chip.full).join("; ")}.`
    : "No selections.";

  return (
    <div className={[styles.bar, className].filter(Boolean).join(" ")}>
      <div
        ref={toolbarRef}
        role="toolbar"
        aria-label="Selections"
        className={styles.toolbar}
        onFocus={handleFocus}
        onKeyDown={handleKeyDown}
      >
        <div className={styles.historyGroup}>
          <button
            type="button"
            className={`button ${styles.barButton} ${styles.barButtonBack}`}
            data-toolbar-key={BACK}
            tabIndex={tabIndexFor(BACK)}
            aria-disabled={!canBack}
            onClick={canBack ? onBack : undefined}
          >
            <Icon name="chevron-left" size={20} />
            Back
          </button>
          <button
            type="button"
            className={`button ${styles.barButton} ${styles.barButtonForward}`}
            data-toolbar-key={FORWARD}
            tabIndex={tabIndexFor(FORWARD)}
            aria-disabled={!canForward}
            onClick={canForward ? onForward : undefined}
          >
            Forward
            <Icon name="chevron-right" size={20} />
          </button>
        </div>

        <button
          type="button"
          className={`button ${styles.barButton}`}
          data-toolbar-key={CLEAR_ALL}
          tabIndex={tabIndexFor(CLEAR_ALL)}
          aria-disabled={!hasSelection}
          onClick={hasSelection ? onClearAll : undefined}
        >
          Clear All
        </button>

        {hasSelection ? (
          <ul role="list" aria-label="Current Selections" className={styles.chips}>
            {chips.map((chip, index) => {
              const descriptionId = `${id}-chip-${index}`;
              return (
                <li key={chip.field} className={styles.chip} title={chip.full}>
                  <span className={styles.chipText} aria-hidden="true">
                    <span className={styles.chipField}>{chip.field}:</span> {chip.short}
                  </span>
                  <span id={descriptionId} className="visually-hidden">
                    {chip.full}
                  </span>
                  <button
                    type="button"
                    className={styles.chipClear}
                    data-toolbar-key={chipKey(chip.field)}
                    tabIndex={tabIndexFor(chipKey(chip.field))}
                    aria-label={`Clear ${chip.field} Selection`}
                    aria-describedby={descriptionId}
                    onClick={(event) => handleClearField(event, chip.field, index)}
                  >
                    <Icon name="close" size={18} />
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className={styles.barEmpty}>
            <span className={styles.barEmptyTitle}>No Selections.</span> Select any value to filter
            everything else.
          </p>
        )}
      </div>

      {/* Announces the new Selection after any change, including Back, Forward, and clears. */}
      <p className="visually-hidden" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>
    </div>
  );
}
