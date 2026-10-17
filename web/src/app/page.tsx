import LiveMap from "@/components/LiveMap";

export default function Home() {
  return (
    <div className="relative flex flex-1 flex-col">
      <div className="h-[calc(100vh-57px)] w-full">
        <LiveMap />
      </div>
      <div className="absolute bottom-4 left-4 z-[1000] rounded-md bg-white/95 p-3 text-xs shadow">
        <div className="mb-1 font-medium">Occupancy</div>
        <Legend color="#3a9a5b" label="Under 70%" />
        <Legend color="#e8a33d" label="70–90%" />
        <Legend color="#d6453d" label="90%+" />
        <div className="mt-1 text-zinc-500">Thick outline = spots opening soon</div>
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="inline-block h-3 w-3 rounded-full" style={{ background: color }} />
      {label}
    </div>
  );
}
