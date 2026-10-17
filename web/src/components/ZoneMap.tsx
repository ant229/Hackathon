"use client";

import "leaflet/dist/leaflet.css";

import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";

import { occupancyColor, useZoneStatus, ZONES } from "@/lib/data";

/** Leaflet map of all zones, colored by live occupancy. Client-only (see LiveMap.tsx). */
export default function ZoneMap() {
  const status = useZoneStatus();

  return (
    <MapContainer center={[40.6085, -75.379]} zoom={15} className="h-full w-full" scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {ZONES.map((z) => {
        const s = status[z.zone_id];
        const occupied = s?.occupied ?? 0;
        const ratio = Math.min(1, occupied / z.capacity);
        const open = Math.max(0, z.capacity - occupied);
        return (
          <CircleMarker
            key={z.zone_id}
            center={[z.lat, z.lng]}
            radius={8 + Math.sqrt(z.capacity) / 2}
            pathOptions={{
              color: z.visitor_allowed ? "#1f2937" : "#9ca3af",
              weight: s?.opening_soon ? 3 : 1,
              fillColor: occupancyColor(ratio),
              fillOpacity: z.visitor_allowed ? 0.75 : 0.3,
            }}
          >
            <Popup>
              <strong>{z.name}</strong>
              <br />
              {open} of {z.capacity} open ({Math.round(ratio * 100)}% full)
              {s?.opening_soon ? (
                <>
                  <br />
                  {s.opening_soon} opening in the next 15 min
                </>
              ) : null}
              <br />
              {z.hourly_rate != null ? `$${z.hourly_rate.toFixed(2)}/hr` : "Rate varies"}
              {z.time_limit_min ? ` · ${z.time_limit_min / 60}h limit` : " · no time limit"}
              <br />
              Pay with {z.pay_app}
              {!z.visitor_allowed && (
                <>
                  <br />
                  <em>Permit holders only</em>
                </>
              )}
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
