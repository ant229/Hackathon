// Selection_History for Explore (Req 11.16–11.20): a pure reducer over a list of
// Selections plus an index. It has no React or DOM dependency, so it runs anywhere;
// lib/useSelectionHistory.ts wraps it in a hook for client components.
//
// - The history starts with one entry, the empty Selection, at index 0.
// - push(selection) drops every entry after the current one (Req 11.18), then
//   appends the new Selection. Pushing a Selection equal to the current one is a
//   no-op, so a click that changes nothing doesn't add a Back step.
// - back and forward move the index and stop at the ends (Req 11.16, 11.17).
// - canBack and canForward drive the disabled state of Back and Forward
//   (Req 11.19, 11.20).
import type { Selection } from "./api";

export type SelectionHistory = {
  /** Normalized Selections, oldest first. Never empty. */
  readonly entries: readonly Selection[];
  /** Position of the current Selection in `entries`. */
  readonly index: number;
};

export type SelectionHistoryAction =
  | { type: "push"; selection: Selection }
  | { type: "back" }
  | { type: "forward" };

// ---------------------------------------------------------------------------
// Selection helpers
// ---------------------------------------------------------------------------

/**
 * Drops fields with no values and repeated values. Field order and value order are
 * kept as given, because the Selection_Bar shows fields in the order people chose them.
 */
export function normalizeSelection(selection: Selection): Selection {
  const out: Selection = {};
  for (const [field, values] of Object.entries(selection)) {
    if (!Array.isArray(values) || values.length === 0) continue;
    out[field] = Array.from(new Set(values));
  }
  return out;
}

/**
 * A stable key for a Selection: equal Selections give equal keys regardless of field
 * or value order. Sorting happens only here, for comparison, never for display.
 */
export function selectionKey(selection: Selection): string {
  const normalized = normalizeSelection(selection);
  const pairs = Object.keys(normalized)
    .sort()
    .map((field) => [field, [...normalized[field]].sort()]);
  return JSON.stringify(pairs);
}

/** True when both Selections pick the same values in the same fields (OR within a field). */
export function selectionsEqual(a: Selection, b: Selection): boolean {
  return selectionKey(a) === selectionKey(b);
}

/** True when the Selection picks nothing. */
export function isEmptySelection(selection: Selection): boolean {
  return Object.keys(normalizeSelection(selection)).length === 0;
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

/** A new history whose only entry is `initial` (the empty Selection by default). */
export function createSelectionHistory(initial: Selection = {}): SelectionHistory {
  return { entries: [normalizeSelection(initial)], index: 0 };
}

/** The current Selection. */
export function current(history: SelectionHistory): Selection {
  return history.entries[history.index];
}

/** True when an earlier Selection exists (Back is enabled). */
export function canBack(history: SelectionHistory): boolean {
  return history.index > 0;
}

/** True when a later Selection exists (Forward is enabled). */
export function canForward(history: SelectionHistory): boolean {
  return history.index < history.entries.length - 1;
}

/** Adds a Selection after the current one and discards the Forward entries. */
export function push(history: SelectionHistory, selection: Selection): SelectionHistory {
  const next = normalizeSelection(selection);
  if (selectionsEqual(next, current(history))) return history;
  const entries = [...history.entries.slice(0, history.index + 1), next];
  return { entries, index: entries.length - 1 };
}

/** Moves to the previous Selection; unchanged at the start. */
export function back(history: SelectionHistory): SelectionHistory {
  return canBack(history) ? { entries: history.entries, index: history.index - 1 } : history;
}

/** Moves to the Selection the most recent Back replaced; unchanged at the end. */
export function forward(history: SelectionHistory): SelectionHistory {
  return canForward(history) ? { entries: history.entries, index: history.index + 1 } : history;
}

/** Reducer form for useReducer. Returns the same object when nothing changes. */
export function selectionHistoryReducer(
  history: SelectionHistory,
  action: SelectionHistoryAction,
): SelectionHistory {
  switch (action.type) {
    case "push":
      return push(history, action.selection);
    case "back":
      return back(history);
    case "forward":
      return forward(history);
    default:
      return history;
  }
}
