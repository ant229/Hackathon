// Explore's Value_State legend: the five states, each with a color swatch, an
// icon, a label, and a one-line meaning, so the state never depends on color alone
// (Req 11.8, 17.7). It sits above the filter panes.
//
// VALUE_STATE_META is the one source of each state's label, icon, and style class.
// FieldPane imports it, so the panes and the legend always agree. No "use client":
// the legend is static and can render on the server or inside a client view.
import type { ValueState } from "../../lib/api";
import { Icon, type IconName } from "../Icons";
import styles from "./Selection.module.css";

export type ValueStateMeta = {
  /** Label shown in the legend and repeated in each value's accessible name. */
  label: string;
  icon: IconName;
  /** One-line meaning for the legend. */
  description: string;
  /** Selection.module.css class holding the state's background and text colors. */
  className: string;
};

/** Legend order: selected first, then the unselected states from most to least related. */
export const VALUE_STATE_ORDER: readonly ValueState[] = [
  "selected",
  "possible",
  "alternative",
  "excluded",
  "selected_excluded",
];

// Explore doesn't use Qlik's green for Selected: green means availability only.
export const VALUE_STATE_META: Record<ValueState, ValueStateMeta> = {
  selected: {
    label: "Selected",
    icon: "check",
    description: "You selected this value.",
    className: styles.stateSelected,
  },
  possible: {
    label: "Possible",
    icon: "circle",
    description: "Appears in the sessions that match.",
    className: styles.statePossible,
  },
  alternative: {
    label: "Alternative",
    icon: "circle-dotted",
    description: "Would match if you cleared this field.",
    className: styles.stateAlternative,
  },
  excluded: {
    label: "Excluded",
    icon: "circle-slash",
    description: "Your selections in other fields rule it out.",
    className: styles.stateExcluded,
  },
  selected_excluded: {
    label: "Selected, Excluded",
    icon: "check",
    description: "Selected, but your selections in other fields rule it out.",
    className: styles.stateSelectedExcluded,
  },
};

export interface StateLegendProps {
  /** Heading level for the "Value States" title. Default 3. */
  headingLevel?: 2 | 3;
  className?: string;
}

export function StateLegend({ headingLevel = 3, className }: StateLegendProps) {
  const Heading = headingLevel === 2 ? "h2" : "h3";

  return (
    <div className={[styles.legend, className].filter(Boolean).join(" ")}>
      <Heading className={styles.legendTitle}>Value States</Heading>
      <ul role="list" className={styles.legendList}>
        {VALUE_STATE_ORDER.map((state) => {
          const meta = VALUE_STATE_META[state];
          return (
            <li key={state} className={styles.legendItem}>
              <span className={`${styles.swatch} ${meta.className}`} aria-hidden="true">
                <Icon name={meta.icon} size={18} className={styles.valueIcon} />
              </span>
              <span className={styles.legendText}>
                <span className={styles.legendLabel}>{meta.label}</span>
                <span className="visually-hidden">: </span>
                <span className={styles.legendDescription}>{meta.description}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
