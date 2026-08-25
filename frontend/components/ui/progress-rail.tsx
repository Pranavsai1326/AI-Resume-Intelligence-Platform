"use client";

import * as React from "react";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

/*
  Recommended-journey navigation (Phase 9E spec section 2). Not a wizard: every step stays
  visible, backward navigation is always allowed, and a step ahead of what's reachable is shown
  disabled with a reason rather than hidden - the rail communicates the recommended order without
  forcing it.
*/

export interface RailStep {
  key: string;
  label: string;
  /** Whether the user can navigate to this step right now. */
  reachable: boolean;
  /** Shown when the step is not reachable, explaining what unlocks it. */
  reason?: string;
  /** Whether the step's minimum work has already been done (renders a check instead of a number). */
  complete?: boolean;
}

export function ProgressRail({
  steps,
  currentKey,
  onSelect,
}: {
  steps: RailStep[];
  currentKey: string;
  onSelect: (key: string) => void;
}) {
  const currentIndex = steps.findIndex((s) => s.key === currentKey);

  return (
    <nav aria-label="Workspace progress" className="border-b border-border">
      {/* Mobile: a compact fraction + current step label. */}
      <div className="flex items-center justify-between py-2 text-sm text-ink-muted sm:hidden">
        <span aria-hidden>
          {Math.max(currentIndex, 0) + 1}/{steps.length}
        </span>
        <span className="font-medium text-ink">{steps[currentIndex]?.label}</span>
      </div>

      {/* Desktop/tablet: full rail. */}
      <ol className="hidden items-stretch gap-1 overflow-x-auto py-2 sm:flex">
        {steps.map((step, index) => {
          const isCurrent = step.key === currentKey;
          return (
            <li key={step.key} className="flex items-center">
              <button
                type="button"
                aria-current={isCurrent ? "step" : undefined}
                aria-label={
                  !step.reachable && step.reason ? `${step.label} - ${step.reason}` : step.label
                }
                title={!step.reachable ? step.reason : undefined}
                disabled={!step.reachable}
                onClick={() => step.reachable && onSelect(step.key)}
                className={cn(
                  "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[length:var(--text-small)] font-medium whitespace-nowrap transition-colors",
                  isCurrent && "bg-accent-soft text-accent",
                  !isCurrent && step.reachable && "text-ink-muted hover:bg-surface-muted hover:text-ink",
                  !step.reachable && "cursor-not-allowed text-ink-subtle/60",
                )}
              >
                {step.complete && !isCurrent ? (
                  <Check aria-hidden className="size-3.5 text-success" />
                ) : (
                  <span aria-hidden className="tabular-nums">
                    {index + 1}.
                  </span>
                )}
                {step.label}
              </button>
              {index < steps.length - 1 ? (
                <span aria-hidden className="mx-0.5 text-border-strong">
                  &rsaquo;
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
