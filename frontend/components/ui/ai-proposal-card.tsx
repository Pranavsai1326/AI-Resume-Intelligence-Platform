"use client";

import * as React from "react";
import { AlertTriangle, Check, Info, Loader2, Sparkles, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/*
  Generalized "AI proposal" interaction (Phase 9E spec sections 14-15): the single pattern every
  AI feature in the product uses - generate, wait, review a proposal with fact-guard findings
  surfaced directly (never hidden or summarised away), accept or discard. Nothing is applied until
  the user explicitly accepts it (AI_ARCHITECTURE.md section 5).

  This component owns only the chrome (trigger/loading/unavailable/error states + the accept/
  discard actions); callers supply the trigger label and render their own proposal body via
  `renderProposal`, since the shape of a rewrite proposal, a cover letter, and an interview
  question list are all different.
*/

export type AiProposalStatus = "idle" | "loading" | "proposal" | "unavailable" | "error";

export function AiProposalCard<T>({
  status,
  proposal,
  error,
  factGuardFindings,
  unavailableReason,
  triggerLabel,
  loadingLabel,
  onGenerate,
  onAccept,
  onDiscard,
  disabled,
  renderProposal,
  icon: Icon = Sparkles,
}: {
  status: AiProposalStatus;
  proposal: T | null;
  error?: string | null;
  /** Findings for the current proposal - pulled out separately since some proposals nest them per-item. */
  factGuardFindings?: string[];
  unavailableReason?: string | null;
  triggerLabel: string;
  loadingLabel?: string;
  onGenerate: () => void;
  onAccept?: () => void;
  onDiscard: () => void;
  disabled?: boolean;
  renderProposal: (proposal: T) => React.ReactNode;
  icon?: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
}) {
  if (status === "idle" || status === "loading") {
    return (
      <Button type="button" variant="ghost" size="sm" onClick={onGenerate} disabled={disabled || status === "loading"}>
        {status === "loading" ? (
          <Loader2 aria-hidden className="animate-spin" />
        ) : (
          <Icon aria-hidden />
        )}
        {status === "loading" ? (loadingLabel ?? "Generating…") : triggerLabel}
      </Button>
    );
  }

  if (status === "error") {
    return (
      <div className="rounded-card border border-danger/40 bg-danger-soft p-3 text-sm text-ink">
        <p>{error ?? "Something went wrong. Please try again."}</p>
        <Button type="button" variant="ghost" size="sm" onClick={onDiscard} className="mt-1 -ml-3">
          Dismiss
        </Button>
      </div>
    );
  }

  if (status === "unavailable") {
    return (
      <div className="flex items-start gap-2 rounded-card border border-border bg-surface-muted p-3 text-sm text-ink-muted">
        <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-ink-subtle" />
        <div>
          <p>{unavailableReason ?? "AI writing is not available right now."}</p>
          <Button type="button" variant="ghost" size="sm" onClick={onDiscard} className="mt-1 -ml-3">
            Close
          </Button>
        </div>
      </div>
    );
  }

  if (!proposal) return null;

  const findings = factGuardFindings ?? [];

  return (
    <div className="space-y-3 rounded-card border border-border-strong bg-surface p-3 text-sm">
      {renderProposal(proposal)}

      {findings.length > 0 ? (
        <div className="space-y-1 rounded-card border border-warning/40 bg-warning-soft p-2">
          <p className="flex items-center gap-1.5 text-xs font-medium text-ink">
            <AlertTriangle aria-hidden className="size-3.5 text-warning" />
            Please double-check before using this
          </p>
          <ul className="ml-5 list-disc space-y-0.5 text-xs text-ink-muted">
            {findings.map((finding) => (
              <li key={finding}>{finding}</li>
            ))}
          </ul>
        </div>
      ) : (
        <Badge variant="success">No unsupported claims detected</Badge>
      )}

      <div className="flex gap-2">
        {onAccept ? (
          <Button type="button" size="sm" onClick={onAccept}>
            <Check aria-hidden />
            Accept
          </Button>
        ) : null}
        <Button type="button" variant="ghost" size="sm" onClick={onDiscard}>
          <X aria-hidden />
          Discard
        </Button>
      </div>
    </div>
  );
}
