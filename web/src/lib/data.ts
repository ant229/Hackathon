"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { useEffect, useState } from "react";

import samples from "@/data/sample_responses.json";
import geo from "@/data/zones.json";

import type { Recommendation, Zone, ZoneProps, ZoneStatus } from "./types";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
export const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

let supabase: SupabaseClient | null = null;
function db() {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return null;
  supabase ??= createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  return supabase;
}

export const dataMode = SUPABASE_URL ? "live" : "mock";

/** Static zone metadata (from fixtures/zones.geojson). */
export const ZONES: Zone[] = geo.features.map((f) => ({
  ...(f.properties as ZoneProps),
  lng: f.geometry.coordinates[0],
  lat: f.geometry.coordinates[1],
}));

export const DESTINATIONS = [
  { id: 1, name: "Zoellner Arts Center" },
  { id: 2, name: "Goodman Stadium" },
  { id: 3, name: "Alumni Memorial Building" },
  { id: 4, name: "3rd St Shops & SteelStacks" },
];

/** Live occupancy per zone. Supabase Realtime when configured, otherwise mock data. */
export function useZoneStatus(): Record<number, ZoneStatus> {
  const [status, setStatus] = useState<Record<number, ZoneStatus>>(() =>
    Object.fromEntries((samples.zone_status as ZoneStatus[]).map((s) => [s.zone_id, s])),
  );

  useEffect(() => {
    const client = db();
    if (!client) return;
    client
      .from("zone_status")
      .select("*")
      .then(({ data }) => {
        if (data) setStatus(Object.fromEntries((data as ZoneStatus[]).map((s) => [s.zone_id, s])));
      });
    const channel = client
      .channel("zone_status")
      .on("postgres_changes", { event: "*", schema: "public", table: "zone_status" }, (p) => {
        const row = p.new as ZoneStatus;
        if (row?.zone_id) setStatus((prev) => ({ ...prev, [row.zone_id]: row }));
      })
      .subscribe();
    return () => {
      client.removeChannel(channel);
    };
  }, []);

  return status;
}

/** Ranked parking options for a destination. Falls back to mock data with no API configured. */
export async function getRecommendation(destination: number, arrival: string): Promise<Recommendation> {
  if (!API_URL) return samples.recommend as Recommendation;
  const params = new URLSearchParams({ destination: String(destination), arrival });
  const r = await fetch(`${API_URL}/recommend?${params}`);
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r.json();
}

export async function runScenario(scenario: "game_day" | "family_weekend" | "clear") {
  if (!API_URL) return samples.demo_scenario;
  const r = await fetch(`${API_URL}/demo/scenario`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ scenario }),
  });
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r.json();
}

/** 0..1 occupancy -> map color. */
export function occupancyColor(ratio: number) {
  if (ratio >= 0.9) return "#d6453d";
  if (ratio >= 0.7) return "#e8a33d";
  return "#3a9a5b";
}
