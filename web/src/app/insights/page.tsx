"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { dataMode, useZoneStatus, ZONES } from "@/lib/data";

// TODO (frontend lane): add the hour x day heatmap from mv_hourly_occupancy
// and dwell/turnover from mv_dwell_turnover (both readable with the Supabase anon key).
export default function InsightsPage() {
  const status = useZoneStatus();
  const rows = ZONES.filter((z) => z.visitor_allowed).map((z) => ({
    name: z.name.replace(/\s*\(.*\)/, ""),
    occupancy: Math.round(((status[z.zone_id]?.occupied ?? 0) / z.capacity) * 100),
  }));

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-6">
      <h1 className="text-xl font-semibold">Insights</h1>
      <p className="mb-4 text-sm text-zinc-500">Current occupancy by zone ({dataMode} data)</p>
      <div className="h-96 rounded-md bg-white p-4 shadow-sm">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ left: 40 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} unit="%" />
            <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v) => `${v}%`} />
            <Bar dataKey="occupancy" fill="#3b6fb6" radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
