"use client";

// Live Zone_Status updates over Server-Sent Events (Req 7.5, 7.9, 7.10, 14.5).
// Opens EventSource(`${API_BASE}/stream`), merges `snapshot` and `status` rows into
// the zones by zone_id, and on a dropped stream shows paused, retries every 3 s,
// and reloads /zones once the stream reopens.
import { useEffect, useMemo, useState } from "react";
import { getZones, STREAM_URL, type StreamPayload, type Zone, type ZoneStatusRow } from "./api";

/** Reconnect interval after a dropped stream (Req 7.9 requires ≤ 5 s). */
const RETRY_MS = 3000;

/** "connecting" before the first open, "live" while open, "paused" after a drop until recovery. */
export type StreamState = "connecting" | "live" | "paused";

export type ZoneStream = {
  /** Zones with the freshest known status; null until zones are available. */
  zones: Zone[] | null;
  /** True while the stream is open and zones are current. */
  live: boolean;
  /** Finer-grained state, so the first connect doesn't read as "Live updates paused". */
  state: StreamState;
};

function isStreamPayload(value: unknown): value is StreamPayload {
  return (
    typeof value === "object" &&
    value !== null &&
    Array.isArray((value as { zones?: unknown }).zones)
  );
}

function isOlder(candidate: string, current: string): boolean {
  const a = Date.parse(candidate);
  const b = Date.parse(current);
  return Number.isFinite(a) && Number.isFinite(b) && a < b;
}

/** Applies the newest stream row per zone; keeps zone identity when nothing changed. */
function mergeZones(base: Zone[] | null, rows: Record<string, ZoneStatusRow>): Zone[] | null {
  if (!base) return null;
  return base.map((zone) => {
    const row = rows[zone.zone_id];
    if (!row || isOlder(row.updated_at, zone.status.updated_at)) return zone;
    const s = zone.status;
    if (
      s.occupied === row.occupied &&
      s.active_sessions === row.active_sessions &&
      s.opening_soon === row.opening_soon &&
      s.updated_at === row.updated_at
    ) {
      return zone;
    }
    return {
      ...zone,
      status: {
        occupied: row.occupied,
        active_sessions: row.active_sessions,
        opening_soon: row.opening_soon,
        updated_at: row.updated_at,
      },
    };
  });
}

/**
 * Follows /stream for live Zone_Status. Pass the zones loaded from /zones; they may
 * arrive after mount (null first), and stream rows received earlier are applied then.
 */
export function useZoneStream(initialZones: Zone[] | null): ZoneStream {
  const [base, setBase] = useState<Zone[] | null>(initialZones);
  const [seenInitial, setSeenInitial] = useState<Zone[] | null>(initialZones);
  const [rows, setRows] = useState<Record<string, ZoneStatusRow>>({});
  const [state, setState] = useState<StreamState>("connecting");

  // Adopt new initial zones from the caller (derived-state pattern, no effect needed).
  if (initialZones !== seenInitial) {
    setSeenInitial(initialZones);
    if (initialZones) setBase(initialZones);
  }

  useEffect(() => {
    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;
    let recovering = false;

    const onRows = (ev: MessageEvent<string>) => {
      let payload: unknown;
      try {
        payload = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (!isStreamPayload(payload) || payload.zones.length === 0) return;
      setRows((prev) => {
        const next = { ...prev };
        for (const row of payload.zones) {
          if (row && typeof row.zone_id === "string") next[row.zone_id] = row;
        }
        return next;
      });
    };

    const drop = (es: EventSource) => {
      if (disposed || source !== es) return;
      es.close();
      source = null;
      recovering = true;
      setState("paused");
      if (retryTimer) clearTimeout(retryTimer);
      retryTimer = setTimeout(connect, RETRY_MS);
    };

    const connect = () => {
      retryTimer = null;
      if (disposed) return;
      const es = new EventSource(STREAM_URL);
      source = es;
      es.addEventListener("snapshot", onRows);
      es.addEventListener("status", onRows);
      es.onerror = () => drop(es);
      es.onopen = () => {
        if (disposed || source !== es) return;
        if (!recovering) {
          setState("live");
          return;
        }
        // Reconnected: reload every Zone_Status from /zones before showing Live (Req 7.10).
        getZones().then(
          (res) => {
            if (disposed || source !== es) return;
            recovering = false;
            setBase(res.zones);
            setState("live");
          },
          () => drop(es),
        );
      };
    };

    connect();
    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      source?.close();
      source = null;
    };
  }, []);

  const zones = useMemo(() => mergeZones(base, rows), [base, rows]);
  return { zones, live: state === "live", state };
}
