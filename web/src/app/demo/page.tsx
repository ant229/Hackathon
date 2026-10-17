"use client";

import { useState } from "react";

import { API_URL, runScenario } from "@/lib/data";

const SCENARIOS = [
  { id: "game_day", label: "Start game day", hint: "Fills the Goodman lots and nearby garages" },
  { id: "family_weekend", label: "Start Family Weekend", hint: "Campus visitor zones surge" },
  { id: "clear", label: "Clear demo events", hint: "Back to normal demand" },
] as const;

export default function DemoPage() {
  const [message, setMessage] = useState<string | null>(null);

  async function run(id: (typeof SCENARIOS)[number]["id"]) {
    try {
      const r = await runScenario(id);
      setMessage(r.message);
    } catch (err) {
      setMessage(String(err));
    }
  }

  return (
    <div className="mx-auto w-full max-w-xl px-4 py-6">
      <h1 className="mb-1 text-xl font-semibold">Demo controls</h1>
      <p className="mb-4 text-sm text-zinc-500">
        {API_URL ? "Talking to the live API. The map updates within a minute." : "Mock mode: set NEXT_PUBLIC_API_URL to drive the simulator."}
      </p>
      <div className="flex flex-col gap-3">
        {SCENARIOS.map((s) => (
          <button
            key={s.id}
            onClick={() => run(s.id)}
            className="rounded-md bg-white p-4 text-left shadow-sm hover:bg-zinc-100"
          >
            <div className="font-medium">{s.label}</div>
            <div className="text-sm text-zinc-500">{s.hint}</div>
          </button>
        ))}
      </div>
      {message && <p className="mt-4 text-sm">{message}</p>}
    </div>
  );
}
