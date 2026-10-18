// Explore (Req 11, 12): a server shell with the title and lede; the selection
// bar, filter panes, KPIs, heatmap, and charts live in the client ExploreView.
import type { Metadata } from "next";
import ExploreView from "@/components/explore/ExploreView";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Explore",
  description: "Select any value to see what it includes and what it rules out across parking sessions.",
};

export default function ExplorePage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className="text-title">Explore</h1>
        <p className={styles.lede}>
          Select any value to see which sessions it includes and which values it rules out. Everything shown is an
          aggregate.
        </p>
      </header>
      <ExploreView />
    </div>
  );
}
