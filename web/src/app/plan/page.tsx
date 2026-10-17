"use client";

import { useEffect, useState } from "react";

import { DESTINATIONS, getRecommendation } from "@/lib/data";
import type { Recommendation } from "@/lib/types";

function defaultArrival() {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  d.setMinutes(0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

export default function PlanPage() {
  const [destination, setDestination] = useState(1);
  const [arrival, setArrival] = useState("");
  const [result, setResult] = useState<Recommendation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Read the clock on the client only (Next.js prerenders this page).
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setArrival(defaultArrival()), []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const when = arrival ? new Date(arrival) : new Date();
      setResult(await getRecommendation(destination, when.toISOString()));
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-6">
      <h1 className="mb-4 text-xl font-semibold">Plan a visit</h1>
      <form onSubmit={submit} className="flex flex-col gap-3 rounded-md bg-white p-4 shadow-sm sm:flex-row sm:items-end">
        <label className="flex flex-1 flex-col gap-1 text-sm">
          Going to
          <select
            className="rounded border border-zinc-300 px-2 py-1.5"
            value={destination}
            onChange={(e) => setDestination(Number(e.target.value))}
          >
            {DESTINATIONS.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Arriving
          <input
            type="datetime-local"
            className="rounded border border-zinc-300 px-2 py-1.5"
            value={arrival}
            onChange={(e) => setArrival(e.target.value)}
          />
        </label>
        <button className="rounded bg-zinc-900 px-4 py-2 text-sm text-white disabled:opacity-50" disabled={loading}>
          {loading ? "Finding…" : "Find parking"}
        </button>
      </form>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      {result && (
        <ol className="mt-6 flex flex-col gap-3">
          {result.options.map((o) => (
            <li key={o.zone_id} className="rounded-md bg-white p-4 shadow-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-medium">
                  {o.rank}. {o.name}
                </span>
                <span className="text-sm text-zinc-500">{o.walk_minutes} min walk</span>
              </div>
              <div className="mt-1 text-sm text-zinc-600">
                {Math.round(o.prob_available * 100)}% chance of a spot · ~{o.expected_open} open ·{" "}
                {o.hourly_rate != null ? `$${o.hourly_rate.toFixed(2)}/hr` : "rate varies"}
                {o.time_limit_min ? ` · ${o.time_limit_min / 60}h limit` : ""} · pay with {o.pay_app}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
