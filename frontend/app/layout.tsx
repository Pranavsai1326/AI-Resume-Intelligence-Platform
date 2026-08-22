import type { Metadata } from "next";

import { SessionProvider } from "@/components/session/session-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Resume Intelligence — accountless resume analysis and screening",
  description:
    "Analyse, tailor and screen resumes without an account. Everything is processed in a temporary session and removed automatically.",
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:text-ink focus:shadow"
        >
          Skip to content
        </a>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
