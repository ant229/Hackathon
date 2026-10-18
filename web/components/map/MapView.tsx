"use client";

// Live Map page body (Req 7.4–7.10, 7.12). Loads /zones once, then follows
// /stream through useZoneStream, so the dials update without a reload. The
// overlay panel holds zone details, the Opening Soon list, and All Zones.
//
// Opening Soon (/opening-soon?near=<map center>) refetches 500 ms after the map
// stops moving, and when stream updates arrive, at most every 10 s (Req 7.7).
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/components/ApiError";
import { EmptyState } from "@/components/EmptyState";
import { Icon, type IconName } from "@/components/Icons";
import { getOpeningSoon, getZones, type Zone } from "@/lib/api";
import { useZoneStream, type StreamState } from "@/lib/useZoneStream";
import type { MapCenter } from "./ZoneMap";
import ZonePanel, { type OpeningSoonState } from "./ZonePanel";
import styles from "./MapView.module.css";

// Client-only: Leaflet touches window when it loads.
const ZoneMap = dynamic(() => import("./ZoneMap"), {
  ssr: false,
  loading: () => (
    <p role="status" className={styles.mapLoading}>
      Loading map…
    </p>
  ),
});

const MOVE_DEBOUNCE_MS = 500;
const STREAM_REFETCH_MS = 10_000;

const STREAM_CHIP: Record<StreamState, { icon: IconName; text: string }> = {
  live: { icon: "live-dot", text: "Live" },
  paused: { icon: "warning", text: "Live updates paused" },
  connecting: { icon: "refresh", text: "Connecting…" },
};

const LEGEND = [
  { band: "free", label: "Plenty Free", range: "40% or more free" },
  { band: "tight", label: "Filling Up", range: "15 to 39% free" },
  { band: "full", label: "Nearly Full", range: "Under 15% free" },
] as const;

interface LoadState {
  zones: Zone[] | null;
  error: unknown;
}

export default function MapView() {
  const [load, setLoad] = useState<LoadState>({ zones: null, error: null });
  const [attempt, setAttempt] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [opening, setOpening] = useState<OpeningSoonState>({ data: null, error: null });
  const [center, setCenter] = useState<MapCenter | null>(null);
  const [retry, setRetry] = useState(0);

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

  const { zones, state } = useZoneStream(load.zones);

  const selected = useMemo(() => zones?.find((z) => z.zone_id === selectedId) ?? null, [zones, selectedId]);

  // Debounce map moves (Req 7.7).
  const centerTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleMoveEnd = useCallback((next: MapCenter) => {
    if (centerTimer.current) clearTimeout(centerTimer.current);
    centerTimer.current = setTimeout(() => setCenter(next), MOVE_DEBOUNCE_MS);
  }, []);
  useEffect(
    () => () => {
      if (centerTimer.current) clearTimeout(centerTimer.current);
    },
    [],
  );

  // Fetch Opening Soon for the center, now and then on stream updates, at most every 10 s.
  const lastFetch = useRef(0);
  const streamTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const centerRef = useRef<MapCenter | null>(null);
  const fetchOpening = useCallback(() => {
    const at = centerRef.current;
    if (!at) return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    lastFetch.current = Date.now();
    getOpeningSoon(at.lat, at.lng, { signal: controller.signal }).then(
      (data) => {
        if (!controller.signal.aborted) setOpening({ data, error: null });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setOpening({ data: null, error });
      },
    );
  }, []);

  // New center or Try Again: fetch right away.
  useEffect(() => {
    centerRef.current = center;
    fetchOpening();
  }, [center, retry, fetchOpening]);

  // Stream update: refetch, but not more often than every 10 s.
  useEffect(() => {
    if (!zones || !centerRef.current) return;
    if (streamTimer.current) return;
    const wait = Math.max(0, STREAM_REFETCH_MS - (Date.now() - lastFetch.current));
    streamTimer.current = setTimeout(() => {
      streamTimer.current = null;
      fetchOpening();
    }, wait);
  }, [zones, fetchOpening]);

  useEffect(
    () => () => {
      controllerRef.current?.abort();
      if (streamTimer.current) clearTimeout(streamTimer.current);
    },
    [],
  );

  const chip = STREAM_CHIP[state];
  const [hasPaused, setHasPaused] = useState(false);
  if (state === "paused" && !hasPaused) setHasPaused(true);
  const announcement =
    state === "paused"
      ? "Live updates paused. Park LU is reconnecting."
      : state === "live" && hasPaused
        ? "Live updates resumed."
        : "";

  let body;
  if (zones && zones.length > 0) {
    body = (
      <div className={styles.stage} data-collapsed={collapsed}>
        <ZoneMap
          zones={zones}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onMoveEnd={handleMoveEnd}
          className={styles.map}
        />
        <aside className={`material ${styles.panel}`} aria-label="Zone panel">
          <button
            type="button"
            className={styles.toggle}
            aria-expanded={!collapsed}
            aria-controls="map-panel-body"
            onClick={() => setCollapsed((c) => !c)}
          >
            {selected ? selected.zone_name : "Zones"}
            <span className={styles.toggleHint}>{collapsed ? "Show Details" : "Hide Details"}</span>
          </button>
          <div id="map-panel-body" className={styles.panelBody}>
            <ZonePanel
              zones={zones}
              selected={selected}
              onSelect={(id) => {
                setSelectedId(id);
              }}
              openingSoon={opening}
              onRetryOpeningSoon={() => setRetry((n) => n + 1)}
            />
          </div>
        </aside>
      </div>
    );
  } else if (zones) {
    body = (
      <EmptyState
        icon="map"
        title="No Zones Available"
        description="The Park LU API returned no parking zones. Check fixtures/seed.json, restart the API, then select Try Again."
        action={{ label: "Try Again", onClick: () => setAttempt((n) => n + 1) }}
      />
    );
  } else if (load.error !== null) {
    body = (
      <ApiError
        error={load.error}
        title="Zones Didn’t Load"
        onRetry={() => {
          setLoad({ zones: null, error: null });
          setAttempt((n) => n + 1);
        }}
      />
    );
  } else {
    body = (
      <p role="status" className="text-secondary">
        Loading zones…
      </p>
    );
  }

  return (
    <div className={styles.view}>
      <header className={styles.header}>
        <h1 className="text-title">Live Map</h1>
        <span className={styles.chip} data-state={state}>
          <Icon name={chip.icon} size={16} />
          {chip.text}
        </span>
      </header>
      <p role="status" className="visually-hidden">
        {announcement}
      </p>
      <ul className={styles.legend} aria-label="Availability legend">
        {LEGEND.map((item) => (
          <li key={item.band} className={styles.legendItem}>
            <span className={styles.swatch} data-band={item.band} aria-hidden="true" />
            <span>
              <strong>{item.label}</strong> <span className="text-secondary">{item.range}</span>
            </span>
          </li>
        ))}
      </ul>
      {body}
    </div>
  );
}
