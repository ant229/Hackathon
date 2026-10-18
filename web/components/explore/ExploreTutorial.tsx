"use client";

// A short, friendly "how to use Explore" guide that sits in the Fields column.
// It teaches the one idea that makes the associative model click: selecting a
// value filters everything else, and gray values show what your choice ruled
// out. It is collapsible (open by default on wide screens, closed on compact)
// so it never crowds the filters on a phone.
//
// It uses a real Park LU example so the steps are concrete, and it mirrors the
// five Value_State colors and icons from StateLegend, so the guide and the
// panes always describe the same thing.
import { useId, useState, useSyncExternalStore } from "react";
import { Icon } from "@/components/Icons";
import styles from "./ExploreTutorial.module.css";

const COMPACT_QUERY = "(max-width: 1023.98px)";

function subscribe(onChange: () => void): () => void {
  const mql = window.matchMedia(COMPACT_QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}
const getCompact = () => window.matchMedia(COMPACT_QUERY).matches;
const getServer = () => false;

/** Open by default on wide screens, closed on compact, resolved after mount. */
function useDefaultOpen(): boolean {
  return !useSyncExternalStore(subscribe, getCompact, getServer);
}

const STEPS: { icon: Parameters<typeof Icon>[0]["name"]; title: string; body: string }[] = [
  {
    icon: "demo",
    title: "Pick a value in any field",
    body: "Tap a value, say Day: Saturday. Every other field, the KPIs, the heatmap, and the charts re-filter to just those sessions.",
  },
  {
    icon: "explore",
    title: "Add more to narrow it down",
    body: "Add Event: Lehigh Football Home Game. Values combine with AND across fields, so now you see only Saturday game-day sessions.",
  },
  {
    icon: "circle-slash",
    title: "Watch what turns gray",
    body: "Gray values are ruled out by your picks. If a zone goes gray on game-day Saturdays, it never has sessions then. The gray is the insight.",
  },
  {
    icon: "chevron-left",
    title: "Back out anytime",
    body: "Use Back and Forward to step through your selections, a chip's X to clear one field, or Clear All to start over.",
  },
];

export function ExploreTutorial() {
  const open0 = useDefaultOpen();
  const [open, setOpen] = useState<boolean | null>(null);
  const isOpen = open ?? open0;
  const bodyId = useId();

  return (
    <section className={styles.root} aria-labelledby={`${bodyId}-title`}>
      <h3 className={styles.heading}>
        <button
          type="button"
          className={styles.toggle}
          aria-expanded={isOpen}
          aria-controls={bodyId}
          onClick={() => setOpen(!isOpen)}
        >
          <Icon name="info" size={20} className={styles.headingIcon} />
          <span id={`${bodyId}-title`} className={styles.title}>
            How to Use Explore
          </span>
          <Icon
            name={isOpen ? "chevron-down" : "chevron-right"}
            size={20}
            className={styles.chevron}
          />
        </button>
      </h3>

      <div id={bodyId} className={styles.body} hidden={!isOpen}>
        <p className={styles.lede}>
          Explore works like a conversation with the data. Select anything and everything else
          responds. It is modeled on Qlik&rsquo;s associative engine.
        </p>
        <ol className={styles.steps}>
          {STEPS.map((step, i) => (
            <li key={step.title} className={styles.step}>
              <span className={styles.stepNumber} aria-hidden="true">
                {i + 1}
              </span>
              <div className={styles.stepText}>
                <span className={styles.stepTitle}>
                  <Icon name={step.icon} size={16} className={styles.stepIcon} />
                  {step.title}
                </span>
                <span className={styles.stepBody}>{step.body}</span>
              </div>
            </li>
          ))}
        </ol>
        <p className={styles.tip}>
          <Icon name="check" size={16} className={styles.tipIcon} />
          <span>
            Tip: the color key below names the five states. &ldquo;Alternative&rdquo; means a value
            would match again if you cleared its own field.
          </span>
        </p>
      </div>
    </section>
  );
}

export default ExploreTutorial;
