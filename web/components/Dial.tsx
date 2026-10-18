// The Availability Dial, Park LU's signature element. It echoes BPA's garage
// availability map: more green means more available. A ring fills clockwise in
// proportion to percent free and takes the band color (Req 7.2, 7.3); a Caption
// capsule reads "62% free", and the band label ("Plenty Free") is always present
// as text, visibly or in the accessible name, so color is never the only signal
// (Req 17.7). The arc animates over 300 ms and is instant under reduced motion
// (Req 17.8).
//
// No "use client": the dial is presentational and renders on the server or the
// client. Geometry is shared with renderDialHtml (./dialMarkup.ts), which draws
// the same dial for Leaflet markers.
import {
  DIAL_GEOMETRY,
  DIAL_SIZES,
  dialAccessibleName,
  readDial,
  type DialValue,
} from "./dialMarkup";
import styles from "./Dial.module.css";

export type DialSize = keyof typeof DIAL_SIZES;

export type DialProps = DialValue & {
  /** "sm": 44 px ring (lists, map scale). "lg": 72 px ring with the band label shown. Default "sm". */
  size?: DialSize;
  /** Zone or facility name, prefixed to the accessible name. */
  label?: string;
  /** Show the band label as visible text. Defaults to true for "lg", false for "sm". */
  showBandLabel?: boolean;
  /**
   * Hide the dial from assistive technology because the parent already names it,
   * for example a button whose label includes the zone and "% free".
   */
  decorative?: boolean;
  className?: string;
};

export function Dial(props: DialProps) {
  const { size = "sm", label, showBandLabel = size === "lg", decorative = false, className } = props;
  const reading = readDial(props);
  const g = DIAL_GEOMETRY;
  const px = DIAL_SIZES[size];
  const classes = [styles.dial, styles[size], className].filter(Boolean).join(" ");

  return (
    <span
      className={classes}
      data-band={reading.band.band}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : dialAccessibleName(props, label)}
      aria-hidden={decorative ? true : undefined}
    >
      <svg
        className={styles.ring}
        width={px}
        height={px}
        viewBox={`0 0 ${g.viewBox} ${g.viewBox}`}
        aria-hidden="true"
        focusable="false"
      >
        <circle className={styles.disc} cx={g.center} cy={g.center} r={g.discRadius} />
        <circle
          className={styles.track}
          cx={g.center}
          cy={g.center}
          r={g.radius}
          fill="none"
          strokeWidth={g.stroke}
        />
        <circle
          className={styles.arc}
          cx={g.center}
          cy={g.center}
          r={g.radius}
          fill="none"
          strokeWidth={g.stroke}
          strokeDasharray={g.dashArray}
          transform={g.arcTransform}
          style={{ strokeDashoffset: reading.dashOffset }}
        />
      </svg>
      <span className={`${styles.capsule} tabular-nums`}>{reading.capsuleText}</span>
      {showBandLabel ? <span className={styles.bandLabel}>{reading.band.label}</span> : null}
    </span>
  );
}
