import * as React from "react";

import { cn } from "@/lib/utils";
import type { Provenance } from "@/lib/api-client";

/*
  Quiet, actionable-only confidence indicator (Phase 9D/9E spec section 6). No percentage, no
  badge on every field - a thin border tint plus a one-word link, and only when confidence is
  genuinely low. Most fields render nothing at all.
*/

const LOW_CONFIDENCE_THRESHOLD = 0.55;

export function isLowConfidence(provenance: Provenance | null | undefined): boolean {
  if (!provenance) return false;
  if (provenance.kind !== "extracted") return false;
  return provenance.confidence !== null && provenance.confidence < LOW_CONFIDENCE_THRESHOLD;
}

export function ConfidenceHint({
  provenance,
  onCheck,
  className,
}: {
  provenance: Provenance | null | undefined;
  onCheck?: () => void;
  className?: string;
}) {
  if (!isLowConfidence(provenance)) return null;

  return (
    <button
      type="button"
      onClick={onCheck}
      className={cn(
        "inline-flex items-center gap-1 border-l-2 border-warning pl-1.5 text-[length:var(--text-micro)] font-medium text-warning underline-offset-2 hover:underline",
        className,
      )}
    >
      Check this
    </button>
  );
}

/** Wraps a field/entry with the same subtle left-border tint, for containers rather than a link. */
export function ConfidenceTint({
  provenance,
  children,
  className,
}: {
  provenance: Provenance | null | undefined;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn(isLowConfidence(provenance) && "border-l-2 border-warning pl-2", className)}>
      {children}
    </div>
  );
}
