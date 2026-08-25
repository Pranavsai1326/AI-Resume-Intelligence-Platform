"use client";

import * as React from "react";
import { AlertTriangle, Check, Info, Loader2, Sparkles, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, api, type RewriteProposal } from "@/lib/api-client";

/*
  "Improve with AI" - reused on the summary and on every bullet.

  Three end states, all shown inline rather than as toasts: unavailable (calm, expected - "AI
  writing is not configured on this deployment", never framed as an error), a proposal with
  fact-guard findings surfaced directly under the after-text (never hidden or summarised away),
  and accept/discard, which only ever updates the caller's local state - nothing is saved to a
  version until the user explicitly saves one (AI_ARCHITECTURE.md section 5: AI never mutates
  content in place).
*/

export function AiRewriteControl({
  documentId,
  sessionId,
  kind,
  text,
  onAccept,
  label = "Improve with AI",
}: {
  documentId: string;
  sessionId: string;
  kind: "bullet" | "summary";
  text: string;
  onAccept: (next: string) => void;
  label?: string;
}) {
  const [status, setStatus] = React.useState<"idle" | "loading" | "done" | "error">("idle");
  const [proposal, setProposal] = React.useState<RewriteProposal | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const run = async () => {
    setStatus("loading");
    setError(null);
    try {
      const result = await api.rewriteText(documentId, kind, text, sessionId);
      setProposal(result);
      setStatus("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the AI rewrite service.");
      setStatus("error");
    }
  };

  const dismiss = () => {
    setStatus("idle");
    setProposal(null);
    setError(null);
  };

  if (status === "idle" || status === "loading") {
    return (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => void run()}
        disabled={status === "loading" || text.trim().length === 0}
      >
        {status === "loading" ? (
          <Loader2 aria-hidden className="animate-spin" />
        ) : (
          <Sparkles aria-hidden />
        )}
        {status === "loading" ? "Asking AI…" : label}
      </Button>
    );
  }

  if (status === "error") {
    return (
      <div className="rounded-card border border-danger/40 bg-danger-soft p-3 text-sm text-ink">
        <p>{error}</p>
        <Button type="button" variant="ghost" size="sm" onClick={dismiss} className="mt-1">
          Dismiss
        </Button>
      </div>
    );
  }

  if (!proposal) return null;

  if (!proposal.available) {
    return (
      <div className="flex items-start gap-2 rounded-card border border-border bg-surface-muted p-3 text-sm text-ink-muted">
        <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-ink-subtle" />
        <div>
          <p>{proposal.unavailable_reason ?? "AI writing is not available right now."}</p>
          <Button type="button" variant="ghost" size="sm" onClick={dismiss} className="mt-1 -ml-3">
            Close
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-card border border-border-strong bg-surface p-3 text-sm">
      <div>
        <p className="text-xs font-medium tracking-wide text-ink-subtle uppercase">Before</p>
        <p className="text-ink-muted">{proposal.before}</p>
      </div>
      <div>
        <p className="text-xs font-medium tracking-wide text-ink-subtle uppercase">After</p>
        <p className="text-ink">{proposal.after}</p>
      </div>

      {proposal.fact_guard_findings.length > 0 ? (
        <div className="space-y-1 rounded-card border border-warning/40 bg-warning-soft p-2">
          <p className="flex items-center gap-1.5 text-xs font-medium text-ink">
            <AlertTriangle aria-hidden className="size-3.5 text-warning" />
            Please double-check before accepting
          </p>
          <ul className="ml-5 list-disc space-y-0.5 text-xs text-ink-muted">
            {proposal.fact_guard_findings.map((finding) => (
              <li key={finding}>{finding}</li>
            ))}
          </ul>
        </div>
      ) : (
        <Badge variant="success">No unsupported claims detected</Badge>
      )}

      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          onClick={() => {
            if (proposal.after) onAccept(proposal.after);
            dismiss();
          }}
        >
          <Check aria-hidden />
          Accept
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={dismiss}>
          <X aria-hidden />
          Discard
        </Button>
      </div>
    </div>
  );
}
