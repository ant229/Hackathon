"use client";

// Home's live block (Req 14.3, 14.4, 14.5). Loads /zones once, then follows
// /stream through useZoneStream, so both headline numbers and the dial strip
// update without a reload.
//
// - Open Spaces Now = Σ(capacity − active_sessions) over visitor zones.
// - Zones Opening Soon = count of zones whose opening_soon > 0.
// - The dial strip is Home's one signature element: four visitor zones that
//   span both operators, street and garage.
//
// Numbers update visually only. They sit outside any live region so a tick
// every few seconds never floods a screen reader; the only announcements are
// "paused" and "resumed" after the stream drops.
import { useEffect, useState, type ReactNode } from "react";
import { ApiError } from "@/components/ApiError";
import { Dial } from "@/components/Dial";
import { EmptyState } from "@/components/EmptyState";
import { Icon, type IconName } from "@/components/Icons";
import { getZones, type Zone } from "@/lib/api";
import { formatLocalTime, formatNumber } from "@/lib/format";
import { useZoneStream, type StreamState } from "@/lib/useZoneStream";
import styles from "./LiveCounts.module.css";

/** Polk Street Garage and E 3rd St (BPA), Zoellner Level 1 and Farrington Square (Lehigh). */
const KEY_ZONE_IDS = ["bpa-polk-garage", "bpa-e3rd-west", "lps-zoellner-l1", "lps-farrington"] as const;

const HEADING_ID = "home-live-heading";
const KEY_ZONES_HEADING_ID = "home-key-zones-heading";

const STREAM_CHIP: Record<StreamState, { icon: IconName; text: string }> = {
  live: { icon: "live-dot", text: "Live" },
  paused: { icon: "warning", text: "Live updates paused" },
  connecting: { icon: "refresh", text: "Connecting…" },
};

// ---------------------------------------------------------------------------
// Derived numbers
// ---------------------------------------------------------------------------

interface LiveSummary {
  /** Σ(capacity − active_sessions) over visitor zones (Req 14.3). */
  openSpaces: number;
  visitorCapacity: number;
  visitorZones: number;
  /** Zones with opening_soon > 0 (Req 14.4). */
  openingZones: number;
  /** Σ opening_soon over those zones. */
  openingSpaces: number;
  /** Newest Zone_Status updated_at, as ISO 8601, or null. */
  updatedAt: string | null;
}

function summarize(zones: Zone[]): LiveSummary {
  let openSpaces = 0;
  let visitorCapacity = 0;
  let visitorZones = 0;
  let openingZones = 0;
  let openingSpaces = 0;
  let latest = Number.NEGATIVE_INFINITY;

  for (const zone of zones) {
    if (zone.visitor_allowed) {
      visitorZones += 1;
      visitorCapacity += zone.capacity;
      openSpaces += zone.capacity - zone.status.active_sessions;
    }
    if (zone.status.opening_soon > 0) {
      openingZones += 1;
      openingSpaces += zone.status.opening_soon;
    }
    const t = Date.parse(zone.status.updated_at);
    if (Number.isFinite(t) && t > latest) latest = t;
  }

  return {
    openSpaces,
    visitorCapacity,
    visitorZones,
    openingZones,
    openingSpaces,
    updatedAt: Number.isFinite(latest) ? new Date(latest).toISOString() : null,
  };
}

/** The four key visitor zones in a fixed order, topped up from other visitor zones if any are missing. */
function pickKeyZones(zones: Zone[]): Zone[] {
  const byId = new Map(zones.map((zone) => [zone.zone_id, zone]));
  const picked: Zone[] = [];
  for (const id of KEY_ZONE_IDS) {
    const zone = byId.get(id);
    if (zone?.visitor_allowed) picked.push(zone);
  }
  for (const zone of zones) {
    if (picked.length >= KEY_ZONE_IDS.length) break;
    if (zone.visitor_allowed && !picked.includes(zone)) picked.push(zone);
  }
  return picked;
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface LoadState {
  zones: Zone[] | null;
  error: unknown;
}

export default function LiveCounts() {
  const [load, setLoad] = useState<LoadState>({ zones: null, error: null });
  const [attempt, setAttempt] = useState(0);

  // Load every zone on mount and on Try Again (Req 15.1).
  useEffect(() => {
    const controller = new AbortController();
    getZones({ signal: controller.signal }).then(
      (res) => {
        if (!controller.signal.aborted) setLoad({ zones: res.zones, error: null });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setLoad({ zones: null, error });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  // The stream also reloads /zones when it reconnects, so Home recovers on its
  // own once the API comes back, even after a failed first load.
  const { zones, state } = useZoneStream(load.zones);

  // Announce only a drop and its recovery, never routine ticks or the first connect.
  const [hasPaused, setHasPaused] = useState(false);
  if (state === "paused" && !hasPaused) setHasPaused(true);
  const announcement =
    state === "paused"
      ? "Live updates paused. Park LU is reconnecting."
      : state === "live" && hasPaused
        ? "Live updates resumed."
        : "";

  function retry() {
    setLoad({ zones: null, error: null });
    setAttempt((n) => n + 1);
  }

  const summary = zones ? summarize(zones) : null;
  const chip = STREAM_CHIP[state];

  let body: ReactNode;
  if (zones && zones.length > 0 && summary) {
    body = <LiveBody zones={zones} summary={summary} />;
  } else if (zones) {
    body = (
      <EmptyState
        headingLevel={3}
        icon="map"
        title="No Zones Available"
        description="The Park LU API returned no parking zones. Check fixtures/seed.json, restart the API, then select Try Again."
        action={{ label: "Try Again", onClick: retry }}
      />
    );
  } else if (load.error !== null) {
    body = <ApiError error={load.error} onRetry={retry} headingLevel={3} />;
  } else {
    body = (
      <p role="status" className={`${styles.loading} text-secondary`}>
        Loading live counts…
      </p>
    );
  }

  return (
    <section aria-labelledby={HEADING_ID} className={styles.root}>
      <div className={styles.header}>
        <h2 id={HEADING_ID} className="text-title-3">
          Parking Right Now
        </h2>
        <div className={styles.status}>
          <span className={styles.chip} data-state={state}>
            <Icon name={chip.icon} size={16} className={styles.chipIcon} />
            {chip.text}
          </span>
          {summary?.updatedAt ? (
            <span className={`${styles.updated} tabular-nums`}>
              Updated <time dateTime={summary.updatedAt}>{formatLocalTime(summary.updatedAt)}</time>
            </span>
          ) : null}
        </div>
      </div>
      <p role="status" className="visually-hidden">
        {announcement}
      </p>
      {body}
    </section>
  );
}

function LiveBody({ zones, summary }: { zones: Zone[]; summary: LiveSummary }) {
  const keyZones = pickKeyZones(zones);
  const { openingZones, openingSpaces } = summary;

  const openingDetail =
    openingZones === 0
      ? "zones. No paid time ends in the next 15 minutes."
      : `${plural(openingZones, "zone", "zones")}, where paid time ends for ${formatNumber(openingSpaces)} ` +
        `${plural(openingSpaces, "space", "spaces")} in the next 15 minutes`;

  return (
    <div className={styles.content}>
      <dl className={styles.stats}>
        <div className={styles.stat}>
          <dt className={styles.statLabel}>Open Spaces Now</dt>
          <dd className={styles.statValue}>
            <span className={styles.statNumber}>{formatNumber(summary.openSpaces)}</span>{" "}
            <span className={styles.statDetail}>
              of {formatNumber(summary.visitorCapacity)} visitor spaces, across {summary.visitorZones}{" "}
              {plural(summary.visitorZones, "zone", "zones")}
            </span>
          </dd>
        </div>
        <div className={styles.stat}>
          <dt className={styles.statLabel}>Zones Opening Soon</dt>
          <dd className={styles.statValue}>
            <span className={styles.statNumber}>{formatNumber(openingZones)}</span>{" "}
            <span className={styles.statDetail}>{openingDetail}</span>
          </dd>
        </div>
      </dl>

      {keyZones.length > 0 ? (
        <div className={styles.keyZones}>
          <h3 id={KEY_ZONES_HEADING_ID} className={styles.keyZonesTitle}>
            Key Visitor Zones
          </h3>
          <ul className={styles.places} aria-labelledby={KEY_ZONES_HEADING_ID}>
            {keyZones.map((zone) => (
              <KeyZone key={zone.zone_id} zone={zone} />
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function KeyZone({ zone }: { zone: Zone }) {
  const open = zone.capacity - zone.status.active_sessions;
  return (
    <li className={styles.place}>
      {/* Name first for screen readers; CSS draws the dial on the leading side. */}
      <div className={styles.placeText}>
        <p className={styles.placeName}>{zone.zone_name}</p>
        <p className={styles.placeOpen}>
          <span className="tabular-nums">{formatNumber(open)}</span> of{" "}
          <span className="tabular-nums">{formatNumber(zone.capacity)}</span> spaces open
        </p>
        <p className={styles.placeMeta}>{zone.operator}</p>
        {!zone.enforced ? (
          <p className={styles.placeMeta}>Not enforced now, so occupancy isn’t tracked.</p>
        ) : null}
      </div>
      <Dial occupied={zone.status.occupied} size="lg" className={styles.placeDial} />
    </li>
  );
}
