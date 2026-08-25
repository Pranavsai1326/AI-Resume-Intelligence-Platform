"use client";

import * as React from "react";

import { AiProposalCard, type AiProposalStatus } from "@/components/ui/ai-proposal-card";
import { ApiError, api, type RewriteProposal } from "@/lib/api-client";

/*
  "Improve with AI" - reused on the summary and on every bullet, built on the shared
  AiProposalCard pattern (Phase 9E) so every AI feature in the product behaves identically.
  Nothing is saved to a version until the user explicitly accepts and the caller explicitly saves
  one (AI_ARCHITECTURE.md section 5: AI never mutates content in place).
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
  const [status, setStatus] = React.useState<AiProposalStatus>("idle");
  const [proposal, setProposal] = React.useState<RewriteProposal | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const run = async () => {
    setStatus("loading");
    setError(null);
    try {
      const result = await api.rewriteText(documentId, kind, text, sessionId);
      setProposal(result);
      setStatus(result.available ? "proposal" : "unavailable");
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

  return (
    <AiProposalCard
      status={status}
      proposal={proposal}
      error={error}
      factGuardFindings={proposal?.fact_guard_findings ?? []}
      unavailableReason={proposal?.unavailable_reason}
      triggerLabel={label}
      loadingLabel="Asking AI…"
      disabled={text.trim().length === 0}
      onGenerate={() => void run()}
      onAccept={() => {
        if (proposal?.after) onAccept(proposal.after);
        dismiss();
      }}
      onDiscard={dismiss}
      renderProposal={(p) => (
        <>
          <div>
            <p className="text-xs font-medium tracking-wide text-ink-subtle uppercase">Before</p>
            <p className="text-ink-muted">{p.before}</p>
          </div>
          <div>
            <p className="text-xs font-medium tracking-wide text-ink-subtle uppercase">After</p>
            <p className="text-ink">{p.after}</p>
          </div>
        </>
      )}
    />
  );
}
