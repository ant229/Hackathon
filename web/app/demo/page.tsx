// Demo Control Panel (Req 13.1, 13.7). The server shell renders the title,
// subtitle, and the no-auth note; DemoPanel (client) runs the scenarios.
import type { Metadata } from "next";
import DemoPanel from "@/components/demo/DemoPanel";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Demo Control Panel",
  description: "Spike synthetic parking demand for the Park LU presentation.",
};

export default function DemoPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Demo Control Panel</h1>
        <p className={styles.subtitle}>
          Spike synthetic demand for the presentation. Everything here is simulated.
        </p>
      </header>

      <DemoPanel />

      <p className={styles.footnote}>Local demo only. This panel has no access control.</p>
    </div>
  );
}
