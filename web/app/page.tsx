// Home (Req 14): a server shell with the name, subtitle, and thesis; the live
// numbers and the key-zone dials come from the client LiveCounts. No metadata
// export, so the root layout's default title "Park LU" applies.
import Link from "next/link";
import LiveCounts from "@/components/home/LiveCounts";
import { Icon } from "@/components/Icons";
import styles from "./page.module.css";

const HOW_HEADING_ID = "home-how-heading";
const SOURCES_HEADING_ID = "home-sources-heading";

export default function HomePage() {
  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <p className="eyebrow">South Bethlehem &amp; Lehigh</p>
        <h1 className="text-large-title">Park LU</h1>
        <hr className="gold-rule" aria-hidden="true" />
        <p className={`text-headline ${styles.subtitle}`}>South Bethlehem &amp; Lehigh parking, live</p>
        <p className={styles.thesis}>
          Park LU shows where parking is open around South Bethlehem and Lehigh, and where it will be when you
          arrive.
        </p>
      </header>

      <LiveCounts />

      {/* Next steps (Req 14.6). One prominent action; the rest stay secondary (buttons.md › Style). */}
      <div className={styles.actions}>
        <Link href="/map" className={`button button-primary ${styles.action}`}>
          <Icon name="map" size={20} />
          Open the Live Map
        </Link>
        <Link href="/plan" className={`button ${styles.action}`}>
          <Icon name="plan" size={20} />
          Plan a Visit
        </Link>
        <Link href="/explore" className={`button ${styles.action}`}>
          <Icon name="explore" size={20} />
          Explore the Data
        </Link>
      </div>

      {/* A real sequence: sessions feed occupancy and prediction, which feed Plan and Explore. */}
      <section aria-labelledby={HOW_HEADING_ID} className={styles.section}>
        <h2 id={HOW_HEADING_ID} className="text-title-3">
          How It Works
        </h2>
        <ol role="list" className={styles.steps}>
          <li className={styles.step}>
            <span className={styles.stepNumber} aria-hidden="true">
              1
            </span>
            <h3 className={styles.stepTitle}>Payment Sessions Are the Sensor</h3>
            <p className={styles.stepText}>
              Every pay-by-app session carries a zone, a start time, and a paid-until time. That’s enough to count
              parked cars without cameras or in-ground sensors.
            </p>
          </li>
          <li className={styles.step}>
            <span className={styles.stepNumber} aria-hidden="true">
              2
            </span>
            <h3 className={styles.stepTitle}>Occupancy Now, Prediction Later</h3>
            <p className={styles.stepText}>
              Occupancy now is active sessions ÷ capacity. For a later arrival, Park LU takes the average for that
              hour of the week and multiplies it by an event boost for football, Zoellner shows, and Family Weekend.
            </p>
          </li>
          <li className={styles.step}>
            <span className={styles.stepNumber} aria-hidden="true">
              3
            </span>
            <h3 className={styles.stepTitle}>Plan and Explore</h3>
            <p className={styles.stepText}>
              Plan a Visit ranks visitor parking by predicted availability, price, and walk. Explore works like Qlik:
              select any value to see what it includes and what it rules out.
            </p>
          </li>
        </ol>
      </section>

      {/* Req 14.7, 14.8. */}
      <section aria-labelledby={SOURCES_HEADING_ID} className={styles.section}>
        <h2 id={SOURCES_HEADING_ID} className="text-title-3">
          Data Sources
        </h2>
        <p className={styles.sourcesLede}>
          All data on Park LU is synthetic. A simulator generates pay-by-app sessions from the operators’ published
          rules and keeps them running live. Values not yet verified against a published source are flagged as
          placeholders in the seed data.
        </p>

        <div className={styles.sourcesGrid}>
          <div className={styles.sourceCard}>
            <h3>Calibrated to Published Rules</h3>
            <dl className={styles.rules}>
              <div className={styles.ruleGroup}>
                <dt className={styles.ruleOperator}>Bethlehem Parking Authority (BPA)</dt>
                <dd>
                  <ul className={styles.ruleList}>
                    <li>ParkBethlehem RapidPark: $2.50/hr, 2 H limit</li>
                    <li>ParkBethlehem FlexPark: $1.50/hr, 3 H limit</li>
                    <li>Enforced Mon–Sat, 8 AM–9 PM. Pay with ParkMobile or PayByPhone.</li>
                  </ul>
                </dd>
              </div>
              <div className={styles.ruleGroup}>
                <dt className={styles.ruleOperator}>Lehigh Parking Services</dt>
                <dd>
                  <ul className={styles.ruleList}>
                    <li>Zoellner Garage Level 1: $1.00/hr</li>
                    <li>Farrington Square: $1.00/hr</li>
                    <li>Pay with Passport Parking.</li>
                  </ul>
                </dd>
              </div>
            </dl>
          </div>

          <div className={styles.sourceCard}>
            <h3>Integration Roadmap</h3>
            <ul className={styles.roadmap}>
              <li>
                <span className={styles.roadmapName}>Passport partner API</span>
                <span className={styles.roadmapText}>
                  Lehigh Parking Services sessions, through OAuth credentials issued to approved partners.
                </span>
              </li>
              <li>
                <span className={styles.roadmapName}>ParkMobile partner portal</span>
                <span className={styles.roadmapText}>
                  BPA on-street sessions. BPA also accepts PayByPhone, so ParkMobile alone undercounts.
                </span>
              </li>
              <li>
                <span className={styles.roadmapName}>BPA garage availability map</span>
                <span className={styles.roadmapText}>Ground truth for calibrating the BPA garages.</span>
              </li>
            </ul>
            <p className={styles.footnote}>
              Real integration needs data agreements with BPA and Lehigh Parking Services. Adapter plans are in{" "}
              <code className={styles.code}>docs/integration.md</code>.
            </p>
          </div>
        </div>

        <p className={styles.privacy}>
          <Icon name="info" size={20} className={styles.privacyIcon} />
          <span>No license plates are stored. Everything shown is an aggregate.</span>
        </p>
      </section>
    </div>
  );
}
