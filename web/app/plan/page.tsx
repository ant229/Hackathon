// Plan a Visit (Req 9): a server shell with the view title and lede; the
// interactive form and ranked results live in the client PlanView.
import type { Metadata } from "next";
import PlanView from "@/components/plan/PlanView";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Plan a Visit",
  description: "Pick a destination and an arrival time to get ranked parking around South Bethlehem and Lehigh.",
};

export default function PlanPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className="text-title">Plan a Visit</h1>
        <p className={styles.lede}>
          Know where to park before you leave. Pick a destination and an arrival time, and Park LU ranks the
          visitor parking nearby by predicted availability, price, and walk.
        </p>
      </header>
      <PlanView />
    </div>
  );
}
