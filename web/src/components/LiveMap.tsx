"use client";

import dynamic from "next/dynamic";

// Leaflet touches `window`, so it must never render on the server.
const ZoneMap = dynamic(() => import("./ZoneMap"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center text-sm text-zinc-500">Loading map…</div>,
});

export default function LiveMap() {
  return <ZoneMap />;
}
