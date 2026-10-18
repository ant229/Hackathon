// Live Map (Req 7): a server shell with the title; the map, panel, and lists
// live in the client MapView, which loads Leaflet client-only.
import type { Metadata } from "next";
import MapView from "@/components/map/MapView";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Live Map",
  description: "Live parking availability around South Bethlehem and Lehigh, one dial per zone.",
};

export default function MapPage() {
  return (
    <div className={styles.page}>
      <MapView />
    </div>
  );
}
