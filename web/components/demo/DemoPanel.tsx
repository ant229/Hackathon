"use client";

// Demo Control Panel (Req 13.1, 13.7). Game Day, Family Weekend, and Reset post
// a Scenario to /demo/scenario. The active-scenario card follows /demo/status
// plus a local 1 s timer, and the results table lists each affected zone's
// occupancy before and after as percentages in text, with skipped reasons in
// text. Everything shown is an aggregate: zone names and occupancy only.
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  getDemoStatus,
  postScenario,
  type ActiveScenario,
  type ScenarioAffectedZone,
  type ScenarioName,
  type ScenarioResult,
} from "@/lib/api";
import { formatLocalTime } from "@/lib/format";
import { ApiError } from "@/components/ApiError";
import { EmptyState } from "@/components/EmptyState";
import { Icon } from "@/components/Icons";
import styles from "./DemoPanel.module.css";

type LiveScenario = Exclude<ScenarioName, "reset">;
type SkipReason = NonNullable<ScenarioAffectedZone["skipped_reason"]>;

interface ScenarioTile {
  name: LiveScenario;
  label: string;
  description: string;
  /** Game Day is the demo's headline moment, so it alone gets the prominent style. */
  prominent: boolean;
}

const TILES: readonly ScenarioTile[] = [
  {
    name: "game_day",
    label: "Game Day",
    description: "Lehigh football at Goodman Stadium",
    prominent: true,
  },
  {
    name: "family_weekend",
    label: "Family Weekend",
    description: "Families visiting campus and South Side",
    prominent: false,
  },
];

const LABELS: Record<ScenarioName, string> = {
  game_day: "Game Day",
  family_weekend: "Family Weekend",
  reset: "Reset",
};

const SKIP_LABELS: Record<SkipReason, string> = {
  already_full: "Already Full",
  not_enforced: "Not Enforced Right Now",
};

const SKIP_EXPLANATIONS: Record<SkipReason, string> = {
  already_full: "Already Full: the zone was at 95% or more, so it stayed as it was.",
  not_enforced: "Not Enforced Right Now: no payment rule applies at this hour, so no sessions were added.",
};

const IDLE_MESSAGE = "Each scenario runs for 45 minutes. Starting another one replaces it.";

/** The API deactivates an expired scenario on its next 2 s tick; recheck at this pace until it does. */
const EXPIRY_RECHECK_MS = 3000;

type StatusState =
  | { kind: "loading" }
  | { kind: "ready"; active: ActiveScenario | null }
  | { kind: "error"; error: unknown };

interface ActionFailure {
  scenario: ScenarioName;
  error: unknown;
}

interface ResultState {
  data: ScenarioResult;
  /** When the response arrived (ISO); labels the Reset table, which has no event. */
  receivedAt: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Whole percent of a 0–1 ratio. Before, After, and Change all use it, so the points add up. */
const toPercent = (ratio: number) => Math.round(ratio * 100);

function isAbortError(error: unknown): boolean {
  return typeof error === "object" && error !== null && (error as { name?: unknown }).name === "AbortError";
}

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function progressMessage(name: ScenarioName): string {
  return name === "reset" ? "Resetting the demo…" : `Starting ${LABELS[name]}…`;
}

function completionMessage(result: ScenarioResult): string {
  if (result.scenario === "reset") {
    return result.affected.length > 0
      ? `Reset complete. Demo sessions ended in ${count(result.affected.length, "zone", "zones")}.`
      : "Reset complete. No scenario was running.";
  }
  const name = result.event?.name ?? LABELS[result.scenario];
  const until = result.event ? ` until ${formatLocalTime(result.event.expires_at)}` : "";
  const filled = result.affected.filter((zone) => zone.skipped_reason === null).length;
  const skipped = result.affected.length - filled;
  return `${name} is running${until}. ${count(filled, "zone", "zones")} filled${skipped > 0 ? `, ${skipped} skipped` : ""}.`;
}

function failureMessage(name: ScenarioName): string {
  return name === "reset" ? "Reset didn't complete." : `${LABELS[name]} didn't start.`;
}

/** Whole minutes left, rounded up so the card reads "1 min" until the scenario ends. */
function minutesRemaining(active: ActiveScenario, now: number | null): number {
  const expires = Date.parse(active.expires_at);
  if (now === null || Number.isNaN(expires)) return Math.max(0, Math.round(active.minutes_remaining));
  return Math.max(0, Math.ceil((expires - now) / 60_000));
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

export default function DemoPanel() {
  const uid = useId();
  const [status, setStatus] = useState<StatusState>({ kind: "loading" });
  const [now, setNow] = useState<number | null>(null);
  const [inFlight, setInFlight] = useState<ScenarioName | null>(null);
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [result, setResult] = useState<ResultState | null>(null);
  const [message, setMessage] = useState(IDLE_MESSAGE);

  // Guards double activation before React re-renders the aria-disabled state.
  const inFlightRef = useRef(false);
  const statusRequest = useRef<AbortController | null>(null);
  const lastExpiryCheck = useRef(0);

  /** Fetches /demo/status, cancelling any request it supersedes. State changes only once it settles. */
  const loadStatus = useCallback(() => {
    statusRequest.current?.abort();
    const controller = new AbortController();
    statusRequest.current = controller;
    getDemoStatus({ signal: controller.signal }).then(
      (response) => {
        if (controller.signal.aborted) return;
        setNow(Date.now());
        setStatus({ kind: "ready", active: response.active });
      },
      (error: unknown) => {
        if (controller.signal.aborted || isAbortError(error)) return;
        setStatus({ kind: "error", error });
      },
    );
    return controller;
  }, []);

  useEffect(() => {
    const controller = loadStatus();
    return () => controller.abort();
  }, [loadStatus]);

  const active = status.kind === "ready" ? status.active : null;
  const expiresAt = active ? Date.parse(active.expires_at) : Number.NaN;

  // Local 1 s countdown while a scenario runs.
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);

  // At zero, ask the API again, and keep asking until it reports the scenario ended.
  useEffect(() => {
    if (!active || now === null || Number.isNaN(expiresAt) || now < expiresAt) return;
    if (now - lastExpiryCheck.current < EXPIRY_RECHECK_MS) return;
    lastExpiryCheck.current = now;
    loadStatus();
  }, [active, now, expiresAt, loadStatus]);

  function retryStatus() {
    setStatus({ kind: "loading" });
    loadStatus();
  }

  async function runScenario(name: ScenarioName) {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setInFlight(name);
    setFailure(null);
    setMessage(progressMessage(name));
    try {
      const data = await postScenario(name);
      setResult({ data, receivedAt: new Date().toISOString() });
      setMessage(completionMessage(data));
      loadStatus();
    } catch (error) {
      setFailure({ scenario: name, error });
      setMessage(failureMessage(name));
    } finally {
      inFlightRef.current = false;
      setInFlight(null);
    }
  }

  const busy = inFlight !== null;
  const resetHintId = `${uid}-reset-hint`;

  return (
    <div className={styles.root}>
      <div className={styles.layout}>
        {/* Scenario controls */}
        <section className={styles.controls} aria-labelledby={`${uid}-controls-title`}>
          <h2 id={`${uid}-controls-title`} className="visually-hidden">
            Scenarios
          </h2>

          <div className={styles.tiles}>
            {TILES.map((tile) => {
              const pending = inFlight === tile.name;
              const running = active?.scenario === tile.name;
              const titleId = `${uid}-${tile.name}-title`;
              const descriptionId = `${uid}-${tile.name}-description`;
              const runningId = `${uid}-${tile.name}-running`;
              return (
                <button
                  key={tile.name}
                  type="button"
                  className={[styles.tile, tile.prominent ? styles.tileProminent : ""].filter(Boolean).join(" ")}
                  aria-labelledby={titleId}
                  aria-describedby={running ? `${descriptionId} ${runningId}` : descriptionId}
                  aria-disabled={busy || undefined}
                  data-busy={pending || undefined}
                  onClick={() => void runScenario(tile.name)}
                >
                  {pending ? (
                    <span className={styles.spinner} aria-hidden="true" />
                  ) : (
                    <Icon name="demo" size={28} className={styles.tileIcon} />
                  )}
                  <span className={styles.tileText}>
                    <span id={titleId} className={styles.tileTitle}>
                      {tile.label}
                    </span>
                    <span id={descriptionId} className={styles.tileDescription}>
                      {tile.description}
                    </span>
                    {running ? (
                      <span id={runningId} className={styles.running}>
                        <Icon name="live-dot" size={12} />
                        Running Now
                      </span>
                    ) : null}
                  </span>
                </button>
              );
            })}
          </div>

          <div className={styles.resetRow}>
            <button
              type="button"
              className={`button ${styles.resetButton}`}
              aria-describedby={resetHintId}
              aria-disabled={busy || undefined}
              data-busy={inFlight === "reset" || undefined}
              onClick={() => void runScenario("reset")}
            >
              {inFlight === "reset" ? (
                <span className={`${styles.spinner} ${styles.spinnerSmall}`} aria-hidden="true" />
              ) : (
                <Icon name="refresh" size={20} />
              )}
              Reset
            </button>
            <p id={resetHintId} className={styles.resetHint}>
              Ends the running scenario and its demo sessions.
            </p>
          </div>

          <p role="status" className={styles.statusLine}>
            {message}
          </p>

          {failure ? (
            <ApiError
              error={failure.error}
              onRetry={() => void runScenario(failure.scenario)}
              headingLevel={3}
            />
          ) : null}
        </section>

        {/* Active scenario */}
        <section className={`card ${styles.active}`} aria-labelledby={`${uid}-active-title`}>
          <h2 id={`${uid}-active-title`} className={styles.cardTitle}>
            <Icon name="clock" size={20} className={styles.cardTitleIcon} />
            Active Scenario
          </h2>
          {status.kind === "loading" ? (
            <p className={styles.muted}>Checking for a running scenario…</p>
          ) : null}
          {status.kind === "error" ? (
            <ApiError error={status.error} onRetry={retryStatus} headingLevel={3} />
          ) : null}
          {status.kind === "ready" && active ? <ActiveDetails active={active} now={now} /> : null}
          {status.kind === "ready" && !active ? (
            <>
              <p className={styles.idleTitle}>No Scenario Running</p>
              <p className={styles.muted}>Start Game Day or Family Weekend to spike demand for 45 minutes.</p>
            </>
          ) : null}
        </section>

        {/* Before and after */}
        {result ? (
          <ResultsCard result={result} onStartGameDay={() => void runScenario("game_day")} />
        ) : null}

        {/* Presenter cue */}
        <section className={`card ${styles.cue}`} aria-labelledby={`${uid}-cue-title`}>
          <Icon name="info" className={styles.cueIcon} />
          <div className={styles.cueBody}>
            <h2 id={`${uid}-cue-title`} className={styles.cardTitle}>
              Presenter Cue
            </h2>
            <p>Now open Map. Affected dials turn amber or red within 5 seconds.</p>
            <Link href="/map" className="button">
              <Icon name="map" size={20} />
              Open the Live Map
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Active scenario details
// ---------------------------------------------------------------------------

function ActiveDetails({ active, now }: { active: ActiveScenario; now: number | null }) {
  const minutes = minutesRemaining(active, now);

  return (
    <>
      <p className={styles.eventName}>{active.event_name}</p>
      {minutes > 0 ? (
        <p className={styles.remaining}>
          <span className={`tabular-nums ${styles.remainingValue}`}>{minutes}</span>
          <span className={styles.remainingLabel}>min remaining</span>
        </p>
      ) : (
        <p className={styles.remaining}>
          <span className={styles.remainingLabel}>Ending now…</span>
        </p>
      )}
      <p className={styles.endsAt}>Ends at {formatLocalTime(active.expires_at)}</p>
      <p className={styles.footnote}>Started at {formatLocalTime(active.triggered_at)}</p>
    </>
  );
}

// ---------------------------------------------------------------------------
// Results table
// ---------------------------------------------------------------------------

function ResultsCard({ result, onStartGameDay }: { result: ResultState; onStartGameDay: () => void }) {
  const { data, receivedAt } = result;
  const isReset = data.scenario === "reset";

  if (data.affected.length === 0) {
    return (
      <div className={`card ${styles.results}`}>
        {isReset ? (
          <EmptyState
            title="Nothing to Reset"
            description="No scenario was running, so occupancy didn't change."
            action={{ label: "Start Game Day", onClick: onStartGameDay }}
          />
        ) : (
          <EmptyState
            title="No Zones Affected"
            description={`${LABELS[data.scenario]} has no zones to fill. Open the Live Map to see current availability.`}
            action={{ label: "Open the Live Map", href: "/map" }}
          />
        )}
      </div>
    );
  }

  const title = isReset ? "Reset Results" : `${LABELS[data.scenario]} Results`;
  const meta = isReset
    ? `Reset at ${formatLocalTime(receivedAt)}`
    : data.event
      ? `${data.event.name}, started at ${formatLocalTime(data.event.start_time)}`
      : null;
  const reasons = (["already_full", "not_enforced"] as const).filter((reason) =>
    data.affected.some((zone) => zone.skipped_reason === reason),
  );

  return (
    <div className={`card ${styles.results}`}>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption className={styles.caption}>
            <span className={styles.captionTitle}>{title}</span>
            {meta ? <span className={styles.captionMeta}>{meta}</span> : null}
          </caption>
          <thead>
            <tr>
              <th scope="col">Zone</th>
              <th scope="col" className={styles.num}>
                Before
              </th>
              <th scope="col" className={styles.num}>
                After
              </th>
              <th scope="col" className={styles.num}>
                Change
              </th>
            </tr>
          </thead>
          <tbody>
            {data.affected.map((zone) => (
              <ResultRow key={zone.zone_id} zone={zone} />
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.notes}>
        <p>
          {isReset
            ? "Before includes the demo sessions. After is occupancy once they ended."
            : "Before is occupancy just before the trigger. After includes the demo sessions, which end at Reset or when the scenario expires."}
        </p>
        {reasons.map((reason) => (
          <p key={reason}>{SKIP_EXPLANATIONS[reason]}</p>
        ))}
      </div>
    </div>
  );
}

function ResultRow({ zone }: { zone: ScenarioAffectedZone }) {
  const before = toPercent(zone.occupied_before);
  const after = toPercent(zone.occupied_after);

  return (
    <tr>
      <th scope="row" className={styles.zone}>
        {zone.zone_name}
      </th>
      <td className={styles.num}>{before}%</td>
      <td className={styles.num}>{after}%</td>
      <td className={styles.num}>
        <ChangeText reason={zone.skipped_reason} delta={after - before} />
      </td>
    </tr>
  );
}

function ChangeText({ reason, delta }: { reason: ScenarioAffectedZone["skipped_reason"]; delta: number }) {
  if (reason) return <span className={styles.skipped}>{SKIP_LABELS[reason]}</span>;
  if (delta === 0) return <>No change</>;

  const points = Math.abs(delta);
  return (
    <>
      <span aria-hidden="true" className={styles.delta}>
        {delta > 0 ? "+" : "−"}
        {points} pts
      </span>
      <span className="visually-hidden">
        {delta > 0 ? "Up" : "Down"} {count(points, "percentage point", "percentage points")}
      </span>
    </>
  );
}
