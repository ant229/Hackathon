"use client";

// Live Map canvas: plain Leaflet 1.9.4 with one Availability Dial per zone
// (Req 7.1–7.3, 7.5, 7.11, 7.12, 17.7, 17.8).
//
// Leaflet touches `window` and `document` when its module loads, so load this
// component client-only from a client component:
//
//   const ZoneMap = dynamic(() => import("./ZoneMap"), { ssr: false });
//
// Behavior:
// - Basemap: CARTO light_all or dark_all, following prefers-color-scheme live.
//   If tiles fail, the tile layer is removed, the map falls back to a plain
//   --surface-2 background, and a text note says so. Dials keep updating.
// - Dials: a Leaflet divIcon per zone, drawn by renderDialHtml and updated in
//   place by updateDialElement, so the 300 ms arc transition plays and the map
//   never remounts. Zones that share a facility fan out in a small grid around
//   the facility point instead of stacking.
// - Keyboard: each dial is a focusable role="button" named like "E 3rd St
//   RapidPark West, 12% free, Nearly Full". Enter and Space select it. Tab order
//   follows map reading order: north to south, then west to east.
// - Selection: when selectedId changes the map flies to the zone, or jumps
//   there under prefers-reduced-motion: reduce.
// - onMoveEnd reports the map center after every move, including the initial
//   view, so the page can fetch /opening-soon for it.
//
// Positioning hooks for the page: set --zone-map-inset-top and
// --zone-map-inset-bottom on an ancestor to keep Leaflet's controls and the
// attribution clear of floating panels (maps.md › Best practices).
import "leaflet/dist/leaflet.css";
import "../dialPin.css";

import * as L from "leaflet";
import { useEffect, useRef, useState } from "react";

import type { Zone } from "@/lib/api";
import {
  DIAL_PIN,
  dialAccessibleName,
  renderDialHtml,
  updateDialElement,
  type DialPinInput,
} from "../dialMarkup";
import { Icon } from "../Icons";
import styles from "./ZoneMap.module.css";

export type MapCenter = { lat: number; lng: number };

export type ZoneMapProps = {
  /** Every zone with its current Zone_Status, from /zones merged with /stream. */
  zones: Zone[];
  /** The selected zone, or null. The map flies to it when it changes. */
  selectedId: string | null;
  /** Called with the zone_id when a dial is clicked or activated with Enter or Space. */
  onSelect: (zoneId: string) => void;
  /** Called with the map center after every pan or zoom, and once for the initial view. */
  onMoveEnd?: (center: MapCenter) => void;
  /** Extra class for the outer region, for page-level sizing or radius. */
  className?: string;
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** South Bethlehem and Lehigh, used until zones are available to fit. */
export const DEFAULT_CENTER: L.LatLngTuple = [40.6095, -75.378];
export const DEFAULT_ZOOM = 15;

/** Selecting a zone zooms in to at least this level. */
const SELECT_ZOOM = 16;
/** Brief, cancellable fly-to (motion.md › Providing feedback). */
const FLY_DURATION_S = 0.8;
/** Keeps edge dials, including fanned groups, clear of the map edge. */
const FIT_PADDING: L.PointTuple = [56, 56];
const FIT_MAX_ZOOM = 16;

/** Selected dial paints above its neighbors; hover uses Leaflet's 250 offset. */
const SELECTED_Z_OFFSET = 1000;

/** Grid pitch for zones sharing one facility: a 76 x 66 px pin plus a small gap. */
const FAN_PITCH_X = DIAL_PIN.width + 4;
const FAN_PITCH_Y = DIAL_PIN.height + 6;

/**
 * Tile failures tolerated after tiles have loaded, so one dropped tile doesn't
 * remove the basemap. With no tile loaded yet, the first error falls back.
 */
const TILE_ERROR_LIMIT = 3;

const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors ' +
  '&copy; <a href="https://carto.com/attributions">CARTO</a>';

const DARK_QUERY = "(prefers-color-scheme: dark)";
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function tileUrl(dark: boolean): string {
  const style = dark ? "dark_all" : "light_all";
  return `https://{s}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}{r}.png`;
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

// ---------------------------------------------------------------------------
// Dial layout: fan out zones that share a facility point
// ---------------------------------------------------------------------------

type DialLayout = {
  /** Zones in map reading order: north to south, west to east, then grid order. */
  ordered: Zone[];
  /** Leaflet iconAnchor per zone_id. */
  anchors: Map<string, L.PointTuple>;
};

const pointKey = (zone: Zone) => `${zone.lat.toFixed(6)},${zone.lng.toFixed(6)}`;

/**
 * Zones at the same coordinates (E 3rd St West and East; Zoellner Levels 1–4)
 * get a grid of pixel offsets centered on the facility point, filled row by row
 * in /zones order. The seed lists West before East and Level 1 through 4, so
 * West sits left of East and Level 1 top-left. Pixel offsets keep the spacing
 * constant at every zoom level. A lone zone keeps the default anchor, with its
 * ring centered on the coordinates.
 */
function layoutDials(zones: Zone[]): DialLayout {
  const groups = new Map<string, Zone[]>();
  for (const zone of zones) {
    const key = pointKey(zone);
    const members = groups.get(key);
    if (members) members.push(zone);
    else groups.set(key, [zone]);
  }

  const anchors = new Map<string, L.PointTuple>();
  const rank = new Map<string, number>();
  const [baseX, baseY] = DIAL_PIN.iconAnchor;

  for (const members of groups.values()) {
    const count = members.length;
    const cols = Math.ceil(Math.sqrt(count));
    const rows = Math.ceil(count / cols);

    members.forEach((zone, i) => {
      rank.set(zone.zone_id, i);
      if (count === 1) {
        anchors.set(zone.zone_id, [baseX, baseY]);
        return;
      }
      const row = Math.floor(i / cols);
      const col = i % cols;
      const inRow = Math.min(cols, count - row * cols); // a short last row stays centered
      const dx = (col - (inRow - 1) / 2) * FAN_PITCH_X;
      const dy = (row - (rows - 1) / 2) * FAN_PITCH_Y;
      // Moving the anchor left/up moves the icon right/down by the same amount.
      anchors.set(zone.zone_id, [Math.round(baseX - dx), Math.round(baseY - dy)]);
    });
  }

  const rounded = (n: number) => Number(n.toFixed(6));
  const ordered = [...zones].sort(
    (a, b) =>
      rounded(b.lat) - rounded(a.lat) ||
      rounded(a.lng) - rounded(b.lng) ||
      (rank.get(a.zone_id) ?? 0) - (rank.get(b.zone_id) ?? 0),
  );

  return { ordered, anchors };
}

// ---------------------------------------------------------------------------
// Marker helpers
// ---------------------------------------------------------------------------

type MarkerEntry = {
  marker: L.Marker;
  anchorKey: string;
  selected: boolean;
};

function dialInput(zone: Zone, selected: boolean): DialPinInput {
  return { occupied: zone.status.occupied, label: zone.zone_name, selected };
}

function dialIcon(input: DialPinInput, anchor: L.PointTuple): L.DivIcon {
  return L.divIcon({
    html: renderDialHtml(input),
    className: DIAL_PIN.className,
    iconSize: DIAL_PIN.iconSize,
    iconAnchor: anchor,
  });
}

/**
 * Leaflet sets tabindex and role="button" for keyboard markers; this adds the
 * accessible name with the zone and percent free (Req 7.12) and marks the
 * selected dial as the current item.
 */
function applyMarkerA11y(element: HTMLElement | undefined, zone: Zone, selected: boolean): void {
  if (!element) return;
  element.setAttribute("role", "button");
  element.setAttribute("aria-label", dialAccessibleName({ occupied: zone.status.occupied }, zone.zone_name));
  if (selected) element.setAttribute("aria-current", "true");
  else element.removeAttribute("aria-current");
  element.dataset.zoneId = zone.zone_id;
}

function isActivationKey(event: KeyboardEvent): boolean {
  if (event.altKey || event.ctrlKey || event.metaKey) return false;
  return event.key === "Enter" || event.key === " " || event.key === "Spacebar";
}

/**
 * Fits the view to every zone. Returns false (and shows the default view) when
 * there are no zones or the container has no size yet, so the caller can retry.
 */
function fitToZones(map: L.Map, zones: Zone[]): boolean {
  const size = map.getSize();
  if (zones.length === 0 || size.x === 0 || size.y === 0) {
    map.setView(DEFAULT_CENTER, DEFAULT_ZOOM, { animate: false });
    return false;
  }
  const bounds = L.latLngBounds(zones.map((zone) => [zone.lat, zone.lng] as L.LatLngTuple));
  map.fitBounds(bounds, { padding: FIT_PADDING, maxZoom: FIT_MAX_ZOOM, animate: false });
  return true;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ZoneMap({ zones, selectedId, onSelect, onMoveEnd, className }: ZoneMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef(new Map<string, MarkerEntry>());
  const fittedRef = useRef(false);
  const flownToRef = useRef<string | null>(null);

  // Latest props for Leaflet handlers, which are bound once per map.
  const zonesRef = useRef(zones);
  const onSelectRef = useRef(onSelect);
  const onMoveEndRef = useRef(onMoveEnd);

  const [tilesFailed, setTilesFailed] = useState(false);

  useEffect(() => {
    zonesRef.current = zones;
    onSelectRef.current = onSelect;
    onMoveEndRef.current = onMoveEnd;
  });

  // Create the map once per mount. Strict-mode safe: cleanup removes the map,
  // its layers, and every listener, and the next mount starts fresh.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const markers = markersRef.current;

    const reducedMotion = prefersReducedMotion();
    const map = L.map(container, {
      zoomControl: false,
      attributionControl: false,
      minZoom: 12,
      maxZoom: 19,
      // Zoom and fade animations follow Reduce Motion (accessibility.md › Cognitive).
      zoomAnimation: !reducedMotion,
      fadeAnimation: !reducedMotion,
      markerZoomAnimation: !reducedMotion,
    });
    mapRef.current = map;

    L.control.zoom({ position: "topright", zoomInTitle: "Zoom In", zoomOutTitle: "Zoom Out" }).addTo(map);
    L.control
      .attribution({ position: "bottomright", prefix: '<a href="https://leafletjs.com">Leaflet</a>' })
      .addTo(map);

    // Basemap, following the system appearance, including live changes.
    const darkQuery = window.matchMedia(DARK_QUERY);
    let tiles: L.TileLayer | null = L.tileLayer(tileUrl(darkQuery.matches), {
      subdomains: "abcd",
      maxZoom: 20,
      attribution: TILE_ATTRIBUTION,
    });
    let tilesLoaded = 0;
    let tileErrors = 0;
    const onTileLoad = () => {
      tilesLoaded += 1;
    };
    const onTileError = () => {
      tileErrors += 1;
      if (!tiles || (tilesLoaded > 0 && tileErrors < TILE_ERROR_LIMIT)) return;
      // Plain --surface-2 background from here on; dials and controls stay (Req 7.11).
      // Leaflet's own tileunload handler stays attached, so pending tiles abort.
      const failed = tiles;
      tiles = null;
      failed.off("tileload", onTileLoad).off("tileerror", onTileError);
      failed.remove();
      setTilesFailed(true);
    };
    tiles.on("tileload", onTileLoad).on("tileerror", onTileError);
    tiles.addTo(map);

    const onSchemeChange = () => {
      tiles?.setUrl(tileUrl(darkQuery.matches));
    };
    darkQuery.addEventListener("change", onSchemeChange);

    // Report the center after every move. Attached before the first view, so
    // the page also gets the initial center.
    map.on("moveend", () => {
      if (mapRef.current !== map) return;
      const center = map.getCenter();
      onMoveEndRef.current?.({ lat: center.lat, lng: center.lng });
    });

    fittedRef.current = fitToZones(map, zonesRef.current);

    // Keep Leaflet's size in step with the layout (sidebar breakpoints, panels).
    let resizeFrame = 0;
    const resizeObserver = new ResizeObserver(() => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(() => {
        if (mapRef.current !== map) return;
        map.invalidateSize();
        if (!fittedRef.current && zonesRef.current.length > 0) {
          fittedRef.current = fitToZones(map, zonesRef.current);
        }
      });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      cancelAnimationFrame(resizeFrame);
      darkQuery.removeEventListener("change", onSchemeChange);
      mapRef.current = null;
      map.remove();
      markers.clear();
      fittedRef.current = false;
      flownToRef.current = null;
    };
  }, []);

  // Add, update, and remove dials. Status changes update the existing marker
  // elements in place, so the map never remounts (Req 7.5).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const markers = markersRef.current;

    if (!fittedRef.current && zones.length > 0) {
      fittedRef.current = fitToZones(map, zones);
    }

    const { ordered, anchors } = layoutDials(zones);
    const seen = new Set<string>();

    for (const zone of ordered) {
      const zoneId = zone.zone_id;
      seen.add(zoneId);
      const selected = zoneId === selectedId;
      const input = dialInput(zone, selected);
      const anchor = anchors.get(zoneId) ?? DIAL_PIN.iconAnchor;
      const anchorKey = anchor.join(",");
      let entry = markers.get(zoneId);

      if (!entry) {
        const marker = L.marker([zone.lat, zone.lng], {
          icon: dialIcon(input, anchor),
          keyboard: true,
          riseOnHover: true,
          zIndexOffset: selected ? SELECTED_Z_OFFSET : 0,
        });
        marker.on("click", () => onSelectRef.current(zoneId));
        // Leaflet makes the icon focusable but doesn't activate it from the
        // keyboard, so Enter and Space select here (Req 7.12).
        marker.on("keydown", (event: L.LeafletEvent) => {
          const key = (event as L.LeafletKeyboardEvent).originalEvent;
          if (!isActivationKey(key)) return;
          key.preventDefault(); // Space would otherwise scroll the page
          if (key.repeat) return;
          onSelectRef.current(zoneId);
        });
        marker.addTo(map);
        entry = { marker, anchorKey, selected };
        markers.set(zoneId, entry);
      } else {
        const { marker } = entry;
        const position = marker.getLatLng();
        if (position.lat !== zone.lat || position.lng !== zone.lng) {
          marker.setLatLng([zone.lat, zone.lng]);
        }
        const element = marker.getElement();
        if (entry.anchorKey !== anchorKey || !element || !updateDialElement(element, input)) {
          // Leaflet reuses the icon's <div>, so focus and listeners survive.
          marker.setIcon(dialIcon(input, anchor));
          entry.anchorKey = anchorKey;
        }
        if (entry.selected !== selected) {
          marker.setZIndexOffset(selected ? SELECTED_Z_OFFSET : 0);
          entry.selected = selected;
        }
      }

      applyMarkerA11y(entry.marker.getElement(), zone, selected);
    }

    for (const [zoneId, entry] of markers) {
      if (!seen.has(zoneId)) {
        entry.marker.remove();
        markers.delete(zoneId);
      }
    }
  }, [zones, selectedId]);

  // Fly to a newly selected zone; instant under Reduce Motion (Req 17.8).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!selectedId) {
      flownToRef.current = null;
      return;
    }
    if (flownToRef.current === selectedId) return;
    const zone = zones.find((z) => z.zone_id === selectedId);
    if (!zone) return; // not loaded yet; retried when zones arrive

    flownToRef.current = selectedId;
    const target = L.latLng(zone.lat, zone.lng);
    const zoom = Math.max(map.getZoom(), SELECT_ZOOM);
    if (prefersReducedMotion()) {
      map.setView(target, zoom, { animate: false });
    } else {
      map.flyTo(target, zoom, { duration: FLY_DURATION_S });
    }
  }, [selectedId, zones]);

  const rootClass = [styles.root, className].filter(Boolean).join(" ");

  return (
    <div
      className={rootClass}
      role="region"
      aria-label="Map of parking zones"
      data-tiles={tilesFailed ? "failed" : "ok"}
    >
      <div ref={containerRef} className={styles.map} />
      {/* The live region exists from the start so the note is announced when it appears. */}
      <div role="status" className={styles.status}>
        {tilesFailed ? (
          <p className={styles.tileNote}>
            <Icon name="warning" size={16} className={styles.tileNoteIcon} />
            <span>Map tiles unavailable. Zones still update.</span>
          </p>
        ) : null}
      </div>
    </div>
  );
}

export default ZoneMap;
