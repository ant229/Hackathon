"use client";

// App chrome: one primary <nav> that renders as a bottom tab bar below 768 px
// and as a 220 px sidebar at 768 px and wider (Req 17.11, 17.12). Both layouts
// list the same five destinations, so functionality never changes with width.
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icons";
import styles from "./AppShell.module.css";

interface Destination {
  href: string;
  label: string;
  icon: IconName;
}

const DESTINATIONS: readonly Destination[] = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/map", label: "Map", icon: "map" },
  { href: "/plan", label: "Plan", icon: "plan" },
  { href: "/explore", label: "Explore", icon: "explore" },
  { href: "/demo", label: "Demo", icon: "demo" },
];

/** Home matches only "/"; every other destination also matches its subpaths. */
function isCurrent(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";

  return (
    <div className={styles.shell}>
      <a href="#main" className={styles.skipLink}>
        Skip to Content
      </a>

      <nav aria-label="Primary" className={`material ${styles.nav}`}>
        <div className={styles.brand}>
          <p className={styles.wordmark}>Park LU</p>
          <p className={styles.subtitle}>South Bethlehem &amp; Lehigh parking, live</p>
        </div>
        <ul className={styles.list}>
          {DESTINATIONS.map(({ href, label, icon }) => {
            const current = isCurrent(pathname, href);
            return (
              <li key={href} className={styles.item}>
                <Link
                  href={href}
                  className={styles.tab}
                  aria-current={current ? "page" : undefined}
                >
                  <span className={styles.iconWrap}>
                    <Icon name={icon} className={styles.icon} />
                  </span>
                  <span className={styles.label}>{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <main id="main" tabIndex={-1} className={styles.main}>
        {children}
      </main>
    </div>
  );
}
