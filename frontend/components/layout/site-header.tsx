import Link from "next/link";

import { SessionStatus } from "@/components/session/session-status";

export function SiteHeader({ showSession = false }: { showSession?: boolean }) {
  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2 text-sm font-semibold tracking-tight text-ink"
        >
          <span
            aria-hidden="true"
            className="grid size-7 place-items-center rounded-md bg-accent text-xs font-bold text-white"
          >
            RI
          </span>
          Resume Intelligence
        </Link>
        {showSession ? (
          <SessionStatus />
        ) : (
          <nav aria-label="Primary" className="flex items-center gap-1 text-sm">
            <Link
              href="/workspace"
              className="rounded-md px-3 py-2 font-medium text-ink-muted hover:bg-surface-muted hover:text-ink"
            >
              Open workspace
            </Link>
          </nav>
        )}
      </div>
    </header>
  );
}
