"use client";

import * as React from "react";
import { AlertCircle, AlertTriangle, ListChecks, Loader2, Sparkles } from "lucide-react";

import { Alert, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, api, type ResumeVersion, type TailorProposal } from "@/lib/api-client";

/*
  Tailoring: generate proposals against a job, let the user accept/reject each one individually,
  then apply only the accepted ones as a new version (AI_ARCHITECTURE.md section 5 - proposals are
  never applied silently or in bulk without review).
*/

const MIN_JD_LENGTH = 20;

const KIND_LABEL: Record<TailorProposal["kind"], string> = {
  reorder_skills: "Reorder skills",
  skill_reminder: "Skill reminder",
  bullet_rewrite: "Bullet rewrite",
};

function renderText(value: string | string[] | null): string {
  if (value === null) return "";
  return Array.isArray(value) ? value.join(", ") : value;
}

export function TailorPanel({
  documentId,
  versionId,
  sessionId,
  onApplied,
}: {
  documentId: string;
  versionId: string | null;
  sessionId: string;
  onApplied: (version: ResumeVersion) => void;
}) {
  const [jdText, setJdText] = React.useState("");
  const [status, setStatus] = React.useState<"idle" | "generating" | "ready" | "applying" | "error">(
    "idle",
  );
  const [proposals, setProposals] = React.useState<TailorProposal[]>([]);
  const [accepted, setAccepted] = React.useState<Set<string>>(new Set());
  const [error, setError] = React.useState<string | null>(null);

  const generate = async () => {
    setStatus("generating");
    setError(null);
    try {
      const { job_id } = await api.createJobFromText(jdText, sessionId);
      const result = await api.generateTailorProposals(documentId, job_id, sessionId, versionId);
      setProposals(result);
      setAccepted(new Set(result.filter((p) => !p.requires_ai).map((p) => p.proposal_id)));
      setStatus("ready");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not generate tailoring proposals.",
      );
      setStatus("error");
    }
  };

  const toggle = (proposalId: string) => {
    setAccepted((prev) => {
      const next = new Set(prev);
      if (next.has(proposalId)) next.delete(proposalId);
      else next.add(proposalId);
      return next;
    });
  };

  const apply = async () => {
    setStatus("applying");
    setError(null);
    try {
      const acceptedProposals = proposals.filter((p) => accepted.has(p.proposal_id));
      const version = await api.applyTailorProposals(
        { documentId, versionId, label: "Tailored", proposals: acceptedProposals },
        sessionId,
      );
      onApplied(version);
      setProposals([]);
      setAccepted(new Set());
      setStatus("idle");
      setJdText("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not apply the accepted proposals.");
      setStatus("error");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles aria-hidden className="size-4 text-accent" />
          Tailor to a job
        </CardTitle>
        <p className="text-sm text-ink-muted">
          Paste a job description to get concrete, reviewable edit proposals - nothing is applied
          until you accept it.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <textarea
          value={jdText}
          onChange={(e) => setJdText(e.target.value)}
          rows={6}
          placeholder="Paste the job posting, including a Requirements section..."
          className="w-full rounded-card border border-border-strong bg-surface p-3 text-sm text-ink placeholder:text-ink-subtle focus-visible:outline-none"
          disabled={status === "generating"}
        />

        {status === "error" && error ? (
          <Alert variant="danger">
            <AlertTitle className="flex items-center gap-2">
              <AlertCircle aria-hidden className="size-4" />
              Something went wrong
            </AlertTitle>
            <p className="text-ink-muted">{error}</p>
          </Alert>
        ) : null}

        <Button
          type="button"
          onClick={() => void generate()}
          disabled={jdText.trim().length < MIN_JD_LENGTH || status === "generating"}
        >
          {status === "generating" ? (
            <Loader2 aria-hidden className="animate-spin" />
          ) : (
            <ListChecks aria-hidden />
          )}
          {status === "generating" ? "Generating proposals…" : "Generate proposals"}
        </Button>

        {proposals.length > 0 ? (
          <div className="space-y-3">
            <ul className="space-y-2">
              {proposals.map((proposal) => (
                <li
                  key={proposal.proposal_id}
                  className="rounded-card border border-border-strong bg-surface p-3 text-sm"
                >
                  <label className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={accepted.has(proposal.proposal_id)}
                      onChange={() => toggle(proposal.proposal_id)}
                    />
                    <div className="flex-1 space-y-1.5">
                      <div className="flex items-center gap-2">
                        <Badge variant="accent">{KIND_LABEL[proposal.kind]}</Badge>
                        {proposal.requires_ai ? <Badge variant="neutral">AI-assisted</Badge> : null}
                      </div>
                      <p className="text-ink-muted">{proposal.rationale}</p>
                      {proposal.before !== null || proposal.after !== null ? (
                        <div className="grid gap-1 sm:grid-cols-2">
                          <div>
                            <p className="text-xs font-medium tracking-wide text-ink-subtle uppercase">
                              Before
                            </p>
                            <p className="text-ink-muted">{renderText(proposal.before)}</p>
                          </div>
                          <div>
                            <p className="text-xs font-medium tracking-wide text-ink-subtle uppercase">
                              After
                            </p>
                            <p className="text-ink">{renderText(proposal.after)}</p>
                          </div>
                        </div>
                      ) : null}
                      {proposal.fact_guard_findings.length > 0 ? (
                        <div className="space-y-0.5 rounded-card border border-warning/40 bg-warning-soft p-2">
                          <p className="flex items-center gap-1.5 text-xs font-medium text-ink">
                            <AlertTriangle aria-hidden className="size-3.5 text-warning" />
                            Please double-check before accepting
                          </p>
                          <ul className="ml-5 list-disc text-xs text-ink-muted">
                            {proposal.fact_guard_findings.map((finding) => (
                              <li key={finding}>{finding}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>
                  </label>
                </li>
              ))}
            </ul>
            <Button
              type="button"
              onClick={() => void apply()}
              disabled={status === "applying" || accepted.size === 0}
            >
              {status === "applying" ? (
                <Loader2 aria-hidden className="animate-spin" />
              ) : (
                <ListChecks aria-hidden />
              )}
              {status === "applying"
                ? "Applying…"
                : `Apply ${accepted.size} accepted proposal${accepted.size === 1 ? "" : "s"}`}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
