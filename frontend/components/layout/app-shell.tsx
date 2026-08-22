import * as React from "react";

import { SessionExpiredDialog } from "@/components/session/session-expired-dialog";
import { SiteHeader } from "@/components/layout/site-header";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader showSession />
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        {children}
      </main>
      <footer className="border-t border-border bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-4 text-xs text-ink-subtle sm:px-6">
          Temporary session — no account, and nothing is stored permanently.
        </div>
      </footer>
      <SessionExpiredDialog />
    </div>
  );
}
