// A linear occupancy bar: the fill grows as the zone fills and shifts color
// across the same availability bands as the Dial, green when plenty is free,
// amber while filling up, red when nearly full (Req 7.3). The percent and the
// band label are shown as text, so the meaning is never carried by color alone
// (Req 17.7). The fill width animates over 300 ms and is instant under reduced
// motion (handled in the stylesheet, Req 17.8).
//
// No "use client": it's presentational and renders on the server or client.
import { availabilityBand, percentFree } from "@/lib/format";
import styles from "./OccupancyBar.module.css";

export type OccupancyBarProps = {
  /** Zone_Status occupied ratio (0–1). The bar fills to percent occupied. */
  occupied: number;
  /** Visible caption above the bar. Defaults to the band label. */
  label?: string;
  /** Hide from assistive tech when a parent already names the value. */
  decorative?: boolean;
  /** Hide the text caption above the bar (for dense list rows). */
  hideCaption?: boolean;
  className?: string;
};

export function OccupancyBar({ occupied, label, decorative = false, hideCaption = false, className }: OccupancyBarProps) {
  const free = percentFree(occupied);
  const occupiedPct = 100 - free;
  const band = availabilityBand(free);
  const text = `${occupiedPct}% full · ${band.label}`;

  return (
    <div
      className={[styles.root, className].filter(Boolean).join(" ")}
      data-band={band.band}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : `${text}, ${free}% free`}
      aria-hidden={decorative ? true : undefined}
    >
      {hideCaption ? null : (
        <div className={styles.caption}>
          <span className={styles.captionLabel}>{label ?? band.label}</span>
          <span className={`${styles.captionValue} tabular-nums`}>{occupiedPct}% full</span>
        </div>
      )}
      <div className={styles.track}>
        <div className={styles.fill} style={{ width: `${occupiedPct}%` }} />
      </div>
    </div>
  );
}

export default OccupancyBar;
