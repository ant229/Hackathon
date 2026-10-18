"use client";

// React wrapper around the pure Selection_History reducer in ./selectionHistory.
// Explore keeps one history per page visit. Each new Selection is pushed after the
// API confirms it; Back and Forward return the Selection they move to, so the page
// can re-query it right away (Req 11.16, 11.17).
import { useCallback, useMemo, useReducer } from "react";
import type { Selection } from "./api";
import {
  canBack as historyCanBack,
  canForward as historyCanForward,
  createSelectionHistory,
  current,
  selectionHistoryReducer,
  type SelectionHistory,
} from "./selectionHistory";

export type UseSelectionHistory = {
  /** The current Selection. */
  selection: Selection;
  /** False at the first entry: show Back as disabled (Req 11.19). */
  canBack: boolean;
  /** False at the last entry: show Forward as disabled (Req 11.20). */
  canForward: boolean;
  /** Records a new Selection and discards the Forward entries (Req 11.18). Equal Selections are ignored. */
  push: (selection: Selection) => void;
  /** Moves back and returns the Selection to show, or null at the start. */
  back: () => Selection | null;
  /** Moves forward and returns the Selection to show, or null at the end. */
  forward: () => Selection | null;
  /** The whole history, for debugging or tests. */
  history: SelectionHistory;
};

export function useSelectionHistory(initial: Selection = {}): UseSelectionHistory {
  // The initializer runs once, so a fresh `{}` default on every render is harmless.
  const [history, dispatch] = useReducer(selectionHistoryReducer, initial, createSelectionHistory);

  const push = useCallback((selection: Selection) => dispatch({ type: "push", selection }), []);

  // The returned Selection comes from this render's history. Call these once per
  // event; two calls in the same event would both read the same starting index.
  const back = useCallback((): Selection | null => {
    if (!historyCanBack(history)) return null;
    dispatch({ type: "back" });
    return history.entries[history.index - 1];
  }, [history]);

  const forward = useCallback((): Selection | null => {
    if (!historyCanForward(history)) return null;
    dispatch({ type: "forward" });
    return history.entries[history.index + 1];
  }, [history]);

  return useMemo(
    () => ({
      selection: current(history),
      canBack: historyCanBack(history),
      canForward: historyCanForward(history),
      push,
      back,
      forward,
      history,
    }),
    [history, push, back, forward],
  );
}
