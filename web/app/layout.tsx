import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import AppShell from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Park LU", template: "%s · Park LU" },
  description: "South Bethlehem & Lehigh parking, live",
};

// viewport-fit=cover lets the tab bar sit on env(safe-area-inset-bottom).
// Appearance follows only the system setting (Req 17.6).
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F7F4EF" },
    { media: "(prefers-color-scheme: dark)", color: "#15110E" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
