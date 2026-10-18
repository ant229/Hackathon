"use client";

// Overlay panel for the Live Map (Req 7.6, 7.7, 7.8, 17.9). Three parts:
// the selected zone's details, the Opening Soon list, and an All Zones button
// list that works without the map (Req 7.12). Selecting a row selects the zone,
// and the map flies to it.
import Link from "next/link";
import { ApiError } from "@/components/ApiError";
import { Dial } from "@/components/Dial";
import { EmptyState } from "@/components/EmptyState";
import type { OpeningSoonResponse, Zone } from "@/lib/api";
import { formatHourlyRate, formatLocalTime, formatNumber, formatTimeLimit, percentFree } from "@/lib/format";
import styles from "./ZonePanel.module.css";

export interface OpeningSoonState {
  data: OpeningSoonResponse | null;
  error: unknown;
}

export interface ZonePanelProps {
  zones: Zone[];
  selected: Zone | null;
  onSelect: (zoneId: string) => void;
  openingSoon: OpeningSoonState;
  onRetryOpeningSoon: () => void;
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

export default function ZonePanel({ zones, selected, onSelect, openingSoon, onRetryOpeningSoon }: ZonePanelProps) {
  const names = new Map(zones.map((zone) => [zone.zone_id, zone]));
  return (
    <div className={styles.stack}>
      <section aria-labelledby="zone-details-heading" className={styles.section}>
        <h2 id="zone-details-heading" className="text-headline">
          Zone Details
        </h2>
        {selected ? <ZoneDetails zone={selected} /> : <p className="text-secondary">Select a dial or a zone below to see its details.</p>}
      </section>

      <section aria-labelledby="opening-soon-heading" className={styles.section}>
        <h2 id="opening-soon-heading" className="text-headline">
          Opening Soon
        </h2>
        {openingSoon.error !== null ? (
          <ApiError error={openingSoon.error} onRetry={onRetryOpeningSoon} headingLevel={3} title="Opening Soon Didn’t Load" />
        ) : openingSoon.data === null ? (
          <p role="status" className="text-secondary">
            Loading spaces opening soon…
          </p>
        ) : openingSoon.data.results.length === 0 ? (
          <EmptyState
            headingLevel={3}
            title="No Spaces Opening Soon"
            description="No spaces opening in the next 15 minutes"
            action={{ label: "Plan a Visit", href: "/plan" }}
          />
        ) : (
          <>
            <p className="text-footnote text-secondary">
              Paid time ends in the next {openingSoon.data.window_minutes} minutes, nearest to the map center first.
            </p>
            <ul className={styles.list}>
              {openingSoon.data.results.map((r) => (
                <li key={r.zone_id}>
                  <button
                    type="button"
                    className={styles.row}
                    aria-pressed={selected?.zone_id === r.zone_id}
                    onClick={() => onSelect(r.zone_id)}
                  >
                    <span className={styles.rowText}>
                      <span className={styles.rowName}>{names.get(r.zone_id)?.zone_name ?? r.zone_name}</span>
                      <span className={styles.rowMeta}>
                        {r.facility_name} · {Math.round(r.walk_minutes)} min walk
                      </span>
                    </span>
                    <span className={`${styles.rowValue} tabular-nums`}>
                      {formatNumber(r.opening_soon)} {plural(r.opening_soon, "space", "spaces")}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section aria-labelledby="all-zones-heading" className={styles.section}>
        <h2 id="all-zones-heading" className="text-headline">
          All Zones
        </h2>
        <ul className={styles.list}>
          {zones.map((zone) => (
            <li key={zone.zone_id}>
              <button
                type="button"
                className={styles.row}
                aria-pressed={selected?.zone_id === zone.zone_id}
                onClick={() => onSelect(zone.zone_id)}
              >
                <span className={styles.rowText}>
                  <span className={styles.rowName}>{zone.zone_name}</span>
                  <span className={styles.rowMeta}>{zone.operator}</span>
                </span>
                <Dial occupied={zone.status.occupied} size="sm" decorative />
                <span className="visually-hidden">{`${percentFree(zone.status.occupied)}% free`}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function ZoneDetails({ zone }: { zone: Zone }) {
  const s = zone.status;
  const rate = zone.enforced ? formatHourlyRate(zone.hourly_rate) : "Not enforced now";
  return (
    <div className={styles.details}>
      <div className={styles.detailsHead}>
        <div className={styles.rowText}>
          <p className={styles.rowName}>{zone.zone_name}</p>
          <p className={styles.rowMeta}>{zone.facility_name}</p>
        </div>
        <Dial occupied={s.occupied} size="lg" label={zone.zone_name} />
      </div>
      <dl className={styles.facts}>
        <Fact label="Operator" value={zone.operator} />
        <Fact label="Pay With" value={zone.pay_app.length > 0 ? zone.pay_app.join(", ") : "No pay app"} />
        <Fact label="Rate" value={rate} />
        <Fact label="Time Limit" value={formatTimeLimit(zone.time_limit_min)} />
        <Fact label="Parked" value={`${formatNumber(s.active_sessions)} of ${formatNumber(zone.capacity)} spaces`} />
        <Fact label="Opening Soon" value={`${formatNumber(s.opening_soon)} ${plural(s.opening_soon, "space", "spaces")}`} />
        <Fact label="Updated" value={formatLocalTime(s.updated_at)} />
      </dl>
      {zone.note ? <p className={styles.note}>{zone.note}</p> : null}
      <Link href="/plan" className={`button ${styles.planLink}`}>
        Plan a Visit
      </Link>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.fact}>
      <dt>{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}
