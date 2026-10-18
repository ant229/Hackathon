"use client";

// Plan a Visit (Req 9.1, 9.2, 9.14): pick a destination and an arrival time, and
// Park LU ranks visitor parking by predicted availability, price, and walk.
//
// - Destinations come from /destinations as radio cards in a fieldset (Req 9.1).
// - Arrival is a datetime-local input read as Bethlehem time, plus quick chips;
//   it's sent as ISO 8601 with the America/New_York offset.
// - Once both are chosen, /recommend runs automatically (Req 9.2). Typing is
//   debounced 300 ms, clicks run at once, and superseded requests are aborted.
// - Previous results stay visible while a new request loads; a polite live
//   region says "Finding parking…" and then summarizes the results.
// - Every result shows rate, time limit, walk, pay apps, note, any event
//   warning, and the score components as text (Req 9.14).
import { useEffect, useRef, useState, useSyncExternalStore, type ChangeEvent, type ReactNode } from "react";
import { ApiError } from "@/components/ApiError";
import { Dial } from "@/components/Dial";
import { EmptyState } from "@/components/EmptyState";
import { Icon } from "@/components/Icons";
import { getDestinations, getRecommend, type Destination, type Recommendation, type RecommendResponse } from "@/lib/api";
import {
  formatHourlyRate,
  formatLocalDateTime,
  formatLocalTime,
  formatPercent,
  formatTimeLimit,
  toBethlehemLocalInput,
  toIsoWithOffset,
} from "@/lib/format";
import {
  ARRIVAL_PRESETS,
  DEFAULT_ARRIVAL_PRESET,
  arrivalPresetValue,
  defaultArrivalValue,
  type ArrivalPresetId,
} from "./arrivalPresets";
import styles from "./PlanView.module.css";

/** Results requested per query (the API allows 1–20 and defaults to 5). */
const RESULT_LIMIT = 5;
/** Debounce for typed arrival changes. Clicks (radios, chips, Try Again) run at once. */
const TYPING_DEBOUNCE_MS = 300;

const ARRIVAL_INPUT_ID = "plan-arrival";
const ARRIVAL_HINT_ID = "plan-arrival-hint";
const RESULTS_HEADING_ID = "plan-results-heading";

// ---------------------------------------------------------------------------
// Client-only gate
// ---------------------------------------------------------------------------

// The default arrival ("In 1 Hour") depends on the clock, so the form renders
// only on the client. Server HTML and hydration use the server snapshot (false);
// client-side navigation renders the form immediately.
const subscribeNoop = () => () => {};
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

function useIsClient(): boolean {
  return useSyncExternalStore(subscribeNoop, getClientSnapshot, getServerSnapshot);
}

export default function PlanView() {
  const isClient = useIsClient();
  if (!isClient) {
    return (
      <p role="status" className="text-secondary">
        Loading destinations…
      </p>
    );
  }
  return <PlanForm />;
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

const payAppList = new Intl.ListFormat("en-US", { style: "long", type: "disjunction" });

/** "Pay with ParkMobile or PayByPhone". */
function payWithText(apps: string[]): string | null {
  return apps.length > 0 ? `Pay with ${payAppList.format(apps)}` : null;
}

/** Event start as "7:30 PM" on the arrival's Bethlehem date, otherwise "Sat, Nov 7, 12:00 PM". */
function eventStartText(startIso: string, arrivalIso: string): string {
  const start = new Date(startIso);
  const arrival = new Date(arrivalIso);
  if (Number.isNaN(start.getTime()) || Number.isNaN(arrival.getTime())) return formatLocalDateTime(startIso);
  const sameDay = toBethlehemLocalInput(start).slice(0, 10) === toBethlehemLocalInput(arrival).slice(0, 10);
  return sameDay ? formatLocalTime(start) : formatLocalDateTime(start);
}

/** "Availability 22% · Price 0.60 · Walk 1.00 → Score 0.53". */
function scoreText(r: Recommendation): string {
  return (
    `Availability ${formatPercent(r.predicted_availability)} · Price ${r.price_score.toFixed(2)}` +
    ` · Walk ${r.walk_score.toFixed(2)} → Score ${r.score.toFixed(2)}`
  );
}

/** The same components in a form that reads cleanly aloud. */
function scoreSpokenText(r: Recommendation): string {
  return (
    `Availability ${formatPercent(r.predicted_availability)}, price ${r.price_score.toFixed(2)},` +
    ` walk ${r.walk_score.toFixed(2)}, score ${r.score.toFixed(2)}`
  );
}

/** "Ranked by availability (50%), price (20%), and walk (30%)." */
function weightsText(w: RecommendResponse["weights"]): string {
  return (
    `Ranked by availability (${formatPercent(w.availability)}), price (${formatPercent(w.price)}),` +
    ` and walk (${formatPercent(w.walk)}).`
  );
}

/** "5 options for Zoellner Arts Center, arriving Sat, Nov 7, 7:00 PM." */
function summaryText(data: RecommendResponse): string {
  const n = data.results.length;
  return `${n} ${n === 1 ? "option" : "options"} for ${data.destination.name}, arriving ${formatLocalDateTime(data.arrival)}.`;
}

const requestKey = (destinationId: string, arrivalIso: string) => `${destinationId}|${arrivalIso}`;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

interface DestinationsState {
  list: Destination[] | null;
  error: unknown;
}

interface RecommendState {
  /** requestKey of the latest request that started. */
  key: string | null;
  loading: boolean;
  /** Last successful response; kept while a newer request loads. */
  data: RecommendResponse | null;
  error: unknown;
}

const NO_RECOMMENDATIONS: RecommendState = { key: null, loading: false, data: null, error: null };

// ---------------------------------------------------------------------------
// Form and results
// ---------------------------------------------------------------------------

function PlanForm() {
  const [destinations, setDestinations] = useState<DestinationsState>({ list: null, error: null });
  const [destinationsAttempt, setDestinationsAttempt] = useState(0);
  const [destinationId, setDestinationId] = useState<string | null>(null);
  const [arrival, setArrival] = useState<string>(defaultArrivalValue);
  const [activePreset, setActivePreset] = useState<ArrivalPresetId | null>(DEFAULT_ARRIVAL_PRESET);
  const [rec, setRec] = useState<RecommendState>(NO_RECOMMENDATIONS);
  const [recAttempt, setRecAttempt] = useState(0);

  /** Delay before the next /recommend request; set by whichever handler changed the inputs. */
  const delayRef = useRef(0);
  const destinationsRef = useRef<HTMLFieldSetElement>(null);

  const arrivalIso = arrival ? toIsoWithOffset(arrival) : null;
  const currentKey = destinationId && arrivalIso ? requestKey(destinationId, arrivalIso) : null;

  // Load destinations on mount and on Try Again (Req 9.1).
  useEffect(() => {
    const controller = new AbortController();
    getDestinations({ signal: controller.signal }).then(
      (res) => {
        if (!controller.signal.aborted) setDestinations({ list: res.destinations, error: null });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setDestinations({ list: null, error });
      },
    );
    return () => controller.abort();
  }, [destinationsAttempt]);

  // Request recommendations whenever both inputs are set (Req 9.2). Each change
  // cancels the pending timer and aborts the in-flight request it supersedes.
  useEffect(() => {
    if (!destinationId || !arrivalIso) return;
    const key = requestKey(destinationId, arrivalIso);
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setRec((prev) => ({ ...prev, key, loading: true, error: null }));
      getRecommend(destinationId, arrivalIso, RESULT_LIMIT, { signal: controller.signal }).then(
        (data) => {
          if (!controller.signal.aborted) setRec({ key, loading: false, data, error: null });
        },
        (error: unknown) => {
          if (!controller.signal.aborted) setRec((prev) => ({ ...prev, key, loading: false, error }));
        },
      );
    }, delayRef.current);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [destinationId, arrivalIso, recAttempt]);

  function chooseDestination(id: string) {
    delayRef.current = 0;
    setDestinationId(id);
  }

  function choosePreset(id: ArrivalPresetId) {
    delayRef.current = 0;
    setArrival(arrivalPresetValue(id, new Date()));
    setActivePreset(id);
  }

  function editArrival(event: ChangeEvent<HTMLInputElement>) {
    delayRef.current = TYPING_DEBOUNCE_MS;
    setArrival(event.target.value);
    setActivePreset(null);
  }

  function retryDestinations() {
    setDestinations({ list: null, error: null });
    setDestinationsAttempt((n) => n + 1);
  }

  function retryRecommend() {
    delayRef.current = 0;
    setRecAttempt((n) => n + 1);
  }

  /** Moves focus to the destination choices, for the empty states' next action. */
  function focusDestinations() {
    const fieldset = destinationsRef.current;
    if (!fieldset) return;
    const target =
      fieldset.querySelector<HTMLInputElement>('input[type="radio"]:checked') ??
      fieldset.querySelector<HTMLInputElement>('input[type="radio"]');
    target?.focus();
  }

  // ----- Destination choices -----
  let destinationBody: ReactNode;
  if (destinations.error !== null) {
    destinationBody = <ApiError error={destinations.error} onRetry={retryDestinations} headingLevel={3} />;
  } else if (destinations.list === null) {
    destinationBody = (
      <p role="status" className="text-secondary">
        Loading destinations…
      </p>
    );
  } else if (destinations.list.length === 0) {
    destinationBody = (
      <EmptyState
        className="card"
        headingLevel={3}
        icon="pin"
        title="No Destinations Available"
        description="The Park LU API returned no destinations. Check fixtures/seed.json, restart the API, then select Try Again."
        action={{ label: "Try Again", onClick: retryDestinations }}
      />
    );
  } else {
    destinationBody = (
      <div className={styles.options}>
        {destinations.list.map((d) => {
          const selected = d.destination_id === destinationId;
          return (
            <label key={d.destination_id} className={`${styles.option} ${selected ? styles.optionSelected : ""}`}>
              <input
                type="radio"
                name="destination"
                value={d.destination_id}
                checked={selected}
                onChange={() => chooseDestination(d.destination_id)}
                className={styles.radio}
              />
              <span className={styles.indicator} aria-hidden="true">
                {selected ? <Icon name="check" size={16} /> : null}
              </span>
              <span className={styles.optionName}>{d.name}</span>
            </label>
          );
        })}
      </div>
    );
  }

  // ----- Results -----
  const hasDestinations = destinations.list !== null && destinations.list.length > 0;
  const showError = currentKey !== null && rec.key === currentKey && !rec.loading && rec.error !== null;
  const pending = currentKey !== null && !showError && (rec.key !== currentKey || rec.loading);
  const data = currentKey !== null && !showError ? rec.data : null;

  let statusText = "";
  if (pending) statusText = "Finding parking…";
  else if (data) statusText = summaryText(data);

  let resultsBody: ReactNode = null;
  if (!destinationId) {
    resultsBody = (
      <EmptyState
        className={`card ${styles.prompt}`}
        headingLevel={3}
        icon="pin"
        title="Choose a Destination"
        description="Pick where you're going, and Park LU ranks the visitor parking nearby for your arrival time."
        action={hasDestinations ? { label: "Show Destinations", onClick: focusDestinations } : undefined}
      />
    );
  } else if (!arrivalIso) {
    resultsBody = (
      <EmptyState
        className={`card ${styles.prompt}`}
        headingLevel={3}
        icon="clock"
        title="Choose an Arrival Time"
        description="Enter a date and time in Bethlehem time, or pick a quick time such as In 1 Hour."
        action={{ label: "Arrive in 1 Hour", onClick: () => choosePreset("in1h") }}
      />
    );
  } else if (showError) {
    resultsBody = <ApiError error={rec.error} onRetry={retryRecommend} headingLevel={3} />;
  } else if (data && data.results.length > 0) {
    const ranked = [...data.results].sort((a, b) => a.rank - b.rank);
    resultsBody = (
      <>
        <p className="text-footnote text-secondary">{weightsText(data.weights)}</p>
        {/* role="list" keeps list semantics in Safari, which drops them with list-style: none. */}
        <ol role="list" className={styles.list} aria-labelledby={RESULTS_HEADING_ID} aria-busy={pending || undefined}>
          {ranked.map((r) => (
            <ResultCard key={r.zone_id} result={r} arrivalIso={data.arrival} maxWalkMinutes={data.max_walk_minutes} />
          ))}
        </ol>
      </>
    );
  } else if (data && !pending) {
    resultsBody = (
      <EmptyState
        className={`card ${styles.prompt}`}
        headingLevel={3}
        icon="pin"
        title="No Parking Options Found"
        description={`Park LU found no visitor parking for ${data.destination.name} at that time. Choose another destination or arrival time.`}
        action={{ label: "Choose Another Destination", onClick: focusDestinations }}
      />
    );
  }

  return (
    <div className={styles.layout}>
      <form className={styles.form} onSubmit={(event) => event.preventDefault()} aria-label="Plan a Visit">
        <fieldset ref={destinationsRef} className={styles.fieldset}>
          <legend className={styles.sectionTitle}>Where Are You Going?</legend>
          {destinationBody}
        </fieldset>

        <div className={styles.arrival}>
          <label htmlFor={ARRIVAL_INPUT_ID} className={styles.sectionTitle}>
            Arriving
          </label>
          <input
            id={ARRIVAL_INPUT_ID}
            type="datetime-local"
            className={styles.input}
            value={arrival}
            onChange={editArrival}
            aria-describedby={ARRIVAL_HINT_ID}
            aria-invalid={arrivalIso === null ? true : undefined}
          />
          <div role="group" aria-label="Quick Arrival Times" className={styles.chips}>
            {ARRIVAL_PRESETS.map(({ id, label }) => {
              const active = id === activePreset;
              return (
                <button
                  key={id}
                  type="button"
                  className={`${styles.chip} ${active ? styles.chipActive : ""}`}
                  aria-pressed={active}
                  onClick={() => choosePreset(id)}
                >
                  {active ? <Icon name="check" size={16} /> : null}
                  {label}
                </button>
              );
            })}
          </div>
          <p id={ARRIVAL_HINT_ID} className="text-footnote text-secondary">
            {arrivalIso === null
              ? "Enter a date and time, or pick a quick time."
              : "Times are Bethlehem local time (Eastern)."}
          </p>
        </div>
      </form>

      <section className={styles.results} aria-labelledby={RESULTS_HEADING_ID}>
        <div className={styles.resultsHeader}>
          <h2 id={RESULTS_HEADING_ID} className="text-title-3">
            Parking Options
          </h2>
          <p role="status" className={`text-subhead text-secondary ${styles.status}`}>
            {pending ? <span className={styles.spinner} aria-hidden="true" /> : null}
            {statusText}
          </p>
        </div>
        {resultsBody}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Result card
// ---------------------------------------------------------------------------

interface ResultCardProps {
  result: Recommendation;
  /** The response's arrival time, used to format the event start. */
  arrivalIso: string;
  maxWalkMinutes: number;
}

function ResultCard({ result: r, arrivalIso, maxWalkMinutes }: ResultCardProps) {
  const pay = payWithText(r.pay_app);
  const warning = r.event_warning ?? null;

  return (
    <li className={`card ${styles.result}`}>
      <div className={styles.resultHeader}>
        <span className={`${styles.rank} tabular-nums`} aria-hidden="true">
          {r.rank}
        </span>
        <div className={styles.resultTitles}>
          <h3 className="text-headline">
            <span className="visually-hidden">Rank {r.rank}: </span>
            {r.zone_name}
          </h3>
          <p className="text-subhead text-secondary">
            {r.facility_name} · {r.operator}
          </p>
        </div>
        <Dial
          percentFree={Math.round(r.predicted_availability * 100)}
          label="Predicted at arrival"
          showBandLabel
          className={styles.dial}
        />
      </div>

      <dl className={styles.facts}>
        <div className={`${styles.fact} ${r.enforced ? "" : styles.factWide}`}>
          <dt className={styles.factTerm}>Rate</dt>
          <dd className={`${styles.factValue} tabular-nums`}>
            {r.enforced ? formatHourlyRate(r.hourly_rate) : "Not enforced at that time — check posted signs"}
          </dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factTerm}>Time Limit</dt>
          <dd className={`${styles.factValue} tabular-nums`}>{formatTimeLimit(r.time_limit_min)}</dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factTerm}>Walk</dt>
          <dd className={`${styles.factValue} tabular-nums`}>
            {r.walk_minutes} min
            {r.within_walk_limit ? null : <span className={styles.badge}>Beyond {maxWalkMinutes}-min walk</span>}
          </dd>
        </div>
      </dl>

      {pay ? <p className="text-subhead">{pay}</p> : null}

      {r.note ? (
        <p className={`${styles.line} text-subhead text-secondary`}>
          <Icon name="info" size={18} className={styles.lineIcon} />
          <span>{r.note}</span>
        </p>
      ) : null}

      {warning ? (
        <p className={`${styles.line} ${styles.warning} text-subhead`}>
          <Icon name="warning" size={18} className={styles.lineIcon} />
          <span>
            Busier than usual: {warning.event_name} starts {eventStartText(warning.start_time, arrivalIso)}
          </span>
        </p>
      ) : null}

      <p className={`${styles.score} text-footnote text-secondary tabular-nums`}>
        <span aria-hidden="true">{scoreText(r)}</span>
        <span className="visually-hidden">{scoreSpokenText(r)}</span>
      </p>
    </li>
  );
}
