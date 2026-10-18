// Explore KPI row: five aggregate tiles for the Associated_Rows (Req 12.2–12.6).
// A description list pairs each label (dt) with its value (dd). Null values show
// "—" with "Not available" for assistive technology. Only aggregates appear here
// (Req 16.4).
//
// No "use client": the row is presentational and renders anywhere.
import type { ExploreKpis } from "@/lib/api";
import { formatCurrency, formatMinutes, formatNumber, formatPercent } from "@/lib/format";
import styles from "./Charts.module.css";

export type KpiRowProps = {
  kpis: ExploreKpis;
  /** Dims the values and sets aria-busy while a new selection loads. The previous values stay visible. */
  loading?: boolean;
  className?: string;
};

/** Unabbreviated duration for screen readers: 96 → "1 hour 36 minutes" (charts.md › accessibility labels). */
function spokenMinutes(minutes: number): string {
  const total = Math.max(0, Math.round(minutes));
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours} ${hours === 1 ? "hour" : "hours"}`);
  if (rest > 0 || hours === 0) parts.push(`${rest} ${rest === 1 ? "minute" : "minutes"}`);
  return parts.join(" ");
}

type Tile = {
  label: string;
  /** Visible text, or null when the KPI has no value. */
  text: string | null;
  /** Spoken text when it differs from the visible text. */
  spoken?: string;
};

function tiles(kpis: ExploreKpis): Tile[] {
  return [
    { label: "Sessions", text: formatNumber(kpis.sessions) },
    kpis.avg_stay_min === null
      ? { label: "Average Stay", text: null }
      : {
          label: "Average Stay",
          text: formatMinutes(kpis.avg_stay_min),
          spoken: spokenMinutes(kpis.avg_stay_min),
        },
    { label: "Revenue", text: kpis.revenue === null ? null : formatCurrency(kpis.revenue) },
    { label: "Overstay Rate", text: kpis.overstay_rate === null ? null : formatPercent(kpis.overstay_rate) },
    { label: "Average Occupancy", text: kpis.avg_occupancy === null ? null : formatPercent(kpis.avg_occupancy) },
  ];
}

function TileValue({ tile }: { tile: Tile }) {
  if (tile.text === null) {
    return (
      <>
        <span aria-hidden="true">—</span>
        <span className="visually-hidden">Not available</span>
      </>
    );
  }
  if (tile.spoken) {
    return (
      <>
        <span aria-hidden="true">{tile.text}</span>
        <span className="visually-hidden">{tile.spoken}</span>
      </>
    );
  }
  return <>{tile.text}</>;
}

export function KpiRow({ kpis, loading = false, className }: KpiRowProps) {
  const classes = [styles.kpiRow, loading ? styles.kpiLoading : null, className].filter(Boolean).join(" ");
  return (
    <dl className={classes} aria-busy={loading || undefined}>
      {tiles(kpis).map((tile) => (
        <div key={tile.label} className={styles.kpiTile}>
          <dt className={styles.kpiLabel}>{tile.label}</dt>
          <dd className={`${styles.kpiValue} text-title-3 tabular-nums`}>
            <TileValue tile={tile} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default KpiRow;
