import * as React from "react";

import { cn } from "@/lib/utils";

/*
  Plain section-level grouping (Phase 9E): a heading plus content, no outer `Card` border/shadow.
  Reserves `Card` for genuinely distinct, self-contained units (one experience entry, one score
  row) instead of wrapping every page section in a card-in-a-card-in-a-card.
*/

export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
  headingId,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  headingId?: string;
}) {
  return (
    <section className={cn("space-y-4", className)} aria-labelledby={title ? headingId : undefined}>
      {title ? (
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id={headingId} className="text-[length:var(--text-h2)] font-semibold text-ink">
              {title}
            </h2>
            {description ? <p className="mt-1 text-sm text-ink-muted">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}
