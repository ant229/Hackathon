"use client";

// Explore page body (Req 11.9–11.18, 12.1, 12.9–12.14). Loads /explore/model and
// an initial /explore/query for the empty Selection. Every interaction posts the
// new Selection, shows the response, and only then pushes the confirmed Selection
// onto the history. Back and Forward re-query the stored Selection without pushing.
// Previous results stay visible while a query is in flight.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/components/ApiError";
import { EmptyState } from "@/components/EmptyState";
import {
  getExploreModel,
  postExploreQuery,
  postExploreSelect,
  type ExploreModel,
  type ExploreResult,
  type Selection,
} from "@/lib/api";
import { formatMinutes, formatNumber } from "@/lib/format";
import { useSelectionHistory } from "@/lib/useSelectionHistory";
import BarChart from "./BarChart";
import { ExploreTutorial } from "./ExploreTutorial";
import { FieldPane } from "./FieldPane";
import Heatmap from "./Heatmap";
import KpiRow from "./KpiRow";
import { SelectionBar } from "./SelectionBar";
import { StateLegend } from "./StateLegend";
import styles from "./ExploreView.module.css";

const ZONE = "Zone";
const DAY = "Day";
const ARRIVAL_HOUR = "Arrival Hour";
const STAY_LENGTH = "Stay Length";

type Call = (signal: AbortSignal) => Promise<ExploreResult>;

/** The selection with `values` added to `field` (no duplicates). */
function withAdded(selection: Selection, field: string, value: string): Selection {
  const existing = selection[field] ?? [];
  if (existing.includes(value)) return selection;
  return { ...selection, [field]: [...existing, value] };
}

export default function ExploreView() {
  const history = useSelectionHistory({});
  const { selection, push } = history;
  const [model, setModel] = useState<ExploreModel | null>(null);
  const [result, setResult] = useState<ExploreResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  // Latest request wins; a superseded request is aborted and ignored.
  const controllerRef = useRef<AbortController | null>(null);
  const lastRef = useRef<{ call: Call; pushResult: boolean } | null>(null);

  const run = useCallback(
    (
      call: Call,
      { pushResult }: { pushResult: boolean },
    ) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setLoading(true);
      lastRef.current = { call, pushResult };
      call(controller.signal).then(
        (res) => {
          if (controller.signal.aborted) return;
          setResult(res);
          setError(null);
          setLoading(false);
          if (pushResult) push(res.selection);
        },
        (err: unknown) => {
          if (controller.signal.aborted) return;
          setError(err);
          setLoading(false);
        },
      );
    },
    [push],
  );

  // Initial load: model and the empty-Selection query.
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getExploreModel({ signal: controller.signal }),
      postExploreQuery({}, { signal: controller.signal }),
    ]).then(
      ([m, r]) => {
        if (controller.signal.aborted) return;
        setModel(m);
        setResult(r);
        setError(null);
        setLoading(false);
      },
      (err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err);
        setLoading(false);
      },
    );
    return () => controller.abort();
  }, [attempt]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const current = result?.selection ?? selection;

  const query = (next: Selection) =>
    run((signal) => postExploreQuery(next, { signal }), { pushResult: true });

  const onSelectValue = (field: string, value: string) =>
    run((signal) => postExploreSelect(current, field, value, { signal }), { pushResult: true });

  const onClearField = (field: string) => {
    const next = { ...current };
    delete next[field];
    query(next);
  };

  const onBack = () => {
    const target = history.back();
    if (target) run((signal) => postExploreQuery(target, { signal }), { pushResult: false });
  };

  const onForward = () => {
    const target = history.forward();
    if (target) run((signal) => postExploreQuery(target, { signal }), { pushResult: false });
  };

  const onHeatmapSelect = (day: string, hour: number) =>
    query({ ...current, [DAY]: [day], [ARRIVAL_HOUR]: [String(hour)] });

  function retry() {
    if (result && lastRef.current) run(lastRef.current.call, { pushResult: lastRef.current.pushResult });
    else {
      setError(null);
      setLoading(true);
      setAttempt((n) => n + 1);
    }
  }

  if (!result) {
    return error !== null ? (
      <ApiError error={error} title="Explore Didn’t Load" onRetry={retry} />
    ) : (
      <p role="status" className="text-secondary">
        Loading sessions…
      </p>
    );
  }

  const empty = result.kpis.sessions === 0;
  const { charts } = result;
  const hours = (current[ARRIVAL_HOUR] ?? []).map(Number).filter(Number.isFinite);

  return (
    <div className={styles.view}>
      <div className={styles.sticky}>
        <SelectionBar
          selection={current}
          canBack={history.canBack}
          canForward={history.canForward}
          onBack={onBack}
          onForward={onForward}
          onClearAll={() => query({})}
          onClearField={onClearField}
        />
      </div>

      <p role="status" className="visually-hidden">
        {loading ? "Updating results…" : `${formatNumber(result.kpis.sessions)} sessions match the selections.`}
      </p>

      {error !== null ? <ApiError error={error} onRetry={retry} headingLevel={3} /> : null}

      {model ? (
        <p className={`${styles.model} tabular-nums`}>
          {formatNumber(model.row_count)} sessions over {formatNumber(model.history_days)} days
        </p>
      ) : null}

      <div className={styles.layout} aria-busy={loading}>
        <section aria-labelledby="explore-fields-heading" className={styles.fields}>
          <h2 id="explore-fields-heading" className="text-title-3">
            Fields
          </h2>
          <ExploreTutorial />
          <StateLegend headingLevel={3} />
          <div className={styles.panes}>
            {result.fields.map((field) => (
              <FieldPane key={field.name} field={field} onSelectValue={onSelectValue} />
            ))}
          </div>
        </section>

        <section aria-labelledby="explore-results-heading" className={styles.results}>
          <h2 id="explore-results-heading" className="text-title-3">
            Results
          </h2>
          {empty ? (
            <EmptyState
              headingLevel={3}
              icon="explore"
              title="No Sessions Match These Selections"
              description="No sessions match these selections. Clear them to see every session again."
              action={{ label: "Clear All", onClick: () => query({}) }}
            />
          ) : (
            <>
              <KpiRow kpis={result.kpis} loading={loading} />
              <Heatmap
                heatmap={result.heatmap}
                onSelect={onHeatmapSelect}
                selectedDay={current[DAY]}
                selectedHours={hours}
                headingLevel={3}
              />
              <BarChart
                title="Sessions by Zone"
                unitLabel="sessions"
                items={charts.sessions_by_zone.map((z) => ({
                  label: z.zone,
                  value: z.sessions,
                  valueText: formatNumber(z.sessions),
                }))}
                selectedLabels={current[ZONE]}
                onSelect={(zone) => query(withAdded(current, ZONE, zone))}
                maxItems={8}
              />
              <BarChart
                title="Stay Length"
                unitLabel="sessions"
                items={charts.stay_length.map((b) => ({
                  label: b.bucket,
                  value: b.sessions,
                  valueText: formatNumber(b.sessions),
                }))}
                selectedLabels={current[STAY_LENGTH]}
                onSelect={(bucket) => query(withAdded(current, STAY_LENGTH, bucket))}
              />
              <BarChart
                title="Turnover by Zone"
                unitLabel="sessions per space per day"
                items={charts.turnover.map((z) => ({
                  label: z.zone,
                  value: z.sessions_per_space_per_day,
                  valueText: formatNumber(z.sessions_per_space_per_day, 1),
                  detail: `Average stay ${formatMinutes(z.avg_stay_min)}`,
                }))}
                selectedLabels={current[ZONE]}
                onSelect={(zone) => query(withAdded(current, ZONE, zone))}
                maxItems={8}
              />
            </>
          )}
        </section>
      </div>
    </div>
  );
}
