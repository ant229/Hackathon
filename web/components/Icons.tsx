// Park LU interface icons: one inline SVG set on a 24 x 24 grid with a single
// 1.75 stroke weight, drawn in currentColor so icons follow the adjacent text.
// Icons are decorative (aria-hidden). The control that holds an icon carries the
// accessible name, for example a visible label or aria-label.
import type { ReactNode } from "react";

export const ICON_STROKE = 1.75;

const PATHS = {
  // Tabs
  home: (
    <>
      <path d="M4 10.4 12 4l8 6.4V19a1 1 0 0 1-1 1h-4.25v-5.25h-5.5V20H5a1 1 0 0 1-1-1z" />
    </>
  ),
  map: (
    <>
      <path d="M9 4.5 3.75 6.4v13.1L9 17.6l6 2 5.25-1.9V4.6L15 6.5z" />
      <path d="M9 4.5v13.1M15 6.5v13.1" />
    </>
  ),
  plan: (
    <>
      <path d="M12 2.9 21.1 12 12 21.1 2.9 12z" />
      <path d="M9.25 15v-2.75a1.5 1.5 0 0 1 1.5-1.5h4.5" />
      <path d="m13.25 8.75 2 2-2 2" />
    </>
  ),
  explore: (
    <>
      <path d="M4 20h16" />
      <rect x="5.5" y="11" width="3" height="6" rx="1" />
      <rect x="10.5" y="5" width="3" height="12" rx="1" />
      <rect x="15.5" y="8" width="3" height="9" rx="1" />
    </>
  ),
  demo: (
    <>
      <circle cx="12" cy="12" r="8.25" />
      <path d="M10.25 8.9v6.2l5-3.1z" />
    </>
  ),

  // Explore selection states (paired with color and text, Req 11.8)
  check: <path d="m5.5 12.5 4.25 4.25L18.5 7.5" />,
  circle: <circle cx="12" cy="12" r="7.5" />,
  "circle-dotted": <circle cx="12" cy="12" r="7.5" strokeDasharray="1.5 3.2" />,
  "circle-slash": (
    <>
      <circle cx="12" cy="12" r="7.5" />
      <path d="m6.7 17.3 10.6-10.6" />
    </>
  ),

  // Status and feedback
  warning: (
    <>
      <path d="M10.3 4.6 3.2 17.2A2 2 0 0 0 4.9 20h14.2a2 2 0 0 0 1.7-2.8L13.7 4.6a2 2 0 0 0-3.4 0z" />
      <path d="M12 9.5v4" />
      <path d="M12 16.75h.01" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.25" />
      <path d="M12 11v5" />
      <path d="M12 7.75h.01" />
    </>
  ),
  "live-dot": <circle cx="12" cy="12" r="4.5" fill="currentColor" stroke="none" />,
  refresh: (
    <>
      <path d="M19.25 12a7.25 7.25 0 1 1-2.12-5.13" />
      <path d="M19.25 4.75v4.5h-4.5" />
    </>
  ),

  // Navigation and dismissal
  "chevron-left": <path d="m14.5 5.5-6.5 6.5 6.5 6.5" />,
  "chevron-right": <path d="m9.5 5.5 6.5 6.5-6.5 6.5" />,
  "chevron-down": <path d="m5.5 9.5 6.5 6.5 6.5-6.5" />,
  close: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,

  // Parking details
  clock: (
    <>
      <circle cx="12" cy="12" r="8.25" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  walk: (
    <>
      <circle cx="13.5" cy="4.5" r="1.75" />
      <path d="M12.75 8.25 11.5 14l2.25 2.5.75 4" />
      <path d="M11.5 14 10 17.5l-2.25 3" />
      <path d="m12.75 8.25 3 3" />
      <path d="m12.75 8.25-3 1.75-1 3" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21s-6.25-5.4-6.25-10.75a6.25 6.25 0 0 1 12.5 0C18.25 15.6 12 21 12 21z" />
      <circle cx="12" cy="10.25" r="2.25" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

export const ICON_NAMES = Object.keys(PATHS) as IconName[];

export interface IconProps {
  name: IconName;
  /** Rendered width and height in CSS pixels. Defaults to 24. */
  size?: number;
  className?: string;
}

export function Icon({ name, size = 24, className }: IconProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={ICON_STROKE}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
