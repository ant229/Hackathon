import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "South Side Parking",
  description: "Where, when, and for how long parking opens up around Lehigh and South Bethlehem.",
};

const NAV = [
  { href: "/", label: "Live map" },
  { href: "/plan", label: "Plan a visit" },
  { href: "/insights", label: "Insights" },
  { href: "/demo", label: "Demo" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-zinc-50 text-zinc-900">
        <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-zinc-200 bg-white px-4 py-3">
          <span className="font-semibold">South Side Parking</span>
          <nav className="flex flex-wrap gap-4 text-sm">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className="text-zinc-600 hover:text-zinc-900">
                {n.label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="flex flex-1 flex-col">{children}</main>
      </body>
    </html>
  );
}
