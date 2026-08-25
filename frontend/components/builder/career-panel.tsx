"use client";

import * as React from "react";
import { AlertCircle, BookOpen, Loader2, ListChecks, Mail, MessagesSquare } from "lucide-react";

import { AiProposalCard, type AiProposalStatus } from "@/components/ui/ai-proposal-card";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import {
  ApiError,
  api,
  type CoverLetterProposal,
  type InterviewPrepProposal,
  type LearningPriorityResult,
} from "@/lib/api-client";

/*
  Career intelligence (Phase 6, redesigned in 9E): cover letters and interview prep through the
  same AiProposalCard pattern every other AI feature uses, plus learning priorities (Layer 1,
  deterministic, no AI key needed). All three now reuse the job match already computed in the
  Match step - `jobId` is passed down from CandidateWorkspace rather than asking the user to
  paste the job description a second time.
*/

const CATEGORY_LABEL: Record<string, string> = {
  behavioral: "Behavioral",
  technical: "Technical",
  situational: "Situational",
  role_fit: "Role fit",
};

const BUCKET_LABEL: Record<string, string> = {
  missing: "Missing",
  insufficient_evidence: "Worth confirming",
  moderate: "Partial evidence",
};

function CoverLetterCard({
  documentId,
  versionId,
  sessionId,
  jobId,
}: {
  documentId: string;
  versionId: string | null;
  sessionId: string;
  jobId: string;
}) {
  const [status, setStatus] = React.useState<AiProposalStatus>("idle");
  const [result, setResult] = React.useState<CoverLetterProposal | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const generate = async () => {
    setStatus("loading");
    setError(null);
    try {
      const proposal = await api.generateCoverLetter(documentId, jobId, sessionId, versionId);
      setResult(proposal);
      setStatus(proposal.available ? "proposal" : "unavailable");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate a cover letter.");
      setStatus("error");
    }
  };

  return (
    <div className="space-y-2 rounded-card border border-border p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
        <Mail aria-hidden className="size-4 text-accent" />
        Cover letter
      </h3>
      <AiProposalCard
        status={status}
        proposal={result}
        error={error}
        factGuardFindings={result?.fact_guard_findings ?? []}
        unavailableReason={result?.unavailable_reason}
        triggerLabel="Generate cover letter"
        loadingLabel="Writing…"
        icon={Mail}
        onGenerate={() => void generate()}
        onDiscard={() => setStatus("idle")}
        renderProposal={(proposal) => (
          <div className="space-y-2">
            <p className="text-ink">{proposal.salutation}</p>
            {proposal.body_paragraphs.map((paragraph, index) => (
              <p key={index} className="text-ink-muted">
                {paragraph}
              </p>
            ))}
            <p className="text-ink">{proposal.closing}</p>
          </div>
        )}
      />
    </div>
  );
}

function InterviewPrepCard({
  documentId,
  versionId,
  sessionId,
  jobId,
}: {
  documentId: string;
  versionId: string | null;
  sessionId: string;
  jobId: string;
}) {
  const [status, setStatus] = React.useState<AiProposalStatus>("idle");
  const [result, setResult] = React.useState<InterviewPrepProposal | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const generate = async () => {
    setStatus("loading");
    setError(null);
    try {
      const proposal = await api.generateInterviewQuestions(documentId, jobId, sessionId, versionId);
      setResult(proposal);
      setStatus(proposal.available ? "proposal" : "unavailable");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate interview questions.");
      setStatus("error");
    }
  };

  return (
    <div className="space-y-2 rounded-card border border-border p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
        <MessagesSquare aria-hidden className="size-4 text-accent" />
        Interview prep
      </h3>
      <AiProposalCard
        status={status}
        proposal={result}
        error={error}
        unavailableReason={result?.unavailable_reason}
        triggerLabel="Generate interview questions"
        loadingLabel="Preparing…"
        icon={MessagesSquare}
        onGenerate={() => void generate()}
        onDiscard={() => setStatus("idle")}
        factGuardFindings={(result?.questions ?? []).flatMap((q) =>
          q.fact_guard_findings.map((f) => `${q.question}: ${f}`),
        )}
        renderProposal={(proposal) => (
          <ul className="space-y-2">
            {proposal.questions.map((question) => (
              <li key={question.question} className="space-y-1 border-t border-border pt-2 first:border-0 first:pt-0">
                <Badge variant="accent">{CATEGORY_LABEL[question.category] ?? question.category}</Badge>
                <p className="font-medium text-ink">{question.question}</p>
                <p className="text-ink-muted">{question.rationale}</p>
                <p className="text-xs text-ink-subtle">Grounded in: &quot;{question.grounded_in}&quot;</p>
              </li>
            ))}
          </ul>
        )}
      />
    </div>
  );
}

function LearningPrioritiesCard({
  documentId,
  versionId,
  sessionId,
  jobId,
}: {
  documentId: string;
  versionId: string | null;
  sessionId: string;
  jobId: string;
}) {
  const [status, setStatus] = React.useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = React.useState<LearningPriorityResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const generate = async () => {
    setStatus("loading");
    setError(null);
    try {
      const priorities = await api.getLearningPriorities(documentId, jobId, sessionId, versionId);
      setResult(priorities);
      setStatus("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not compute learning priorities.");
      setStatus("error");
    }
  };

  return (
    <div className="space-y-2 rounded-card border border-border p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
        <BookOpen aria-hidden className="size-4 text-accent" />
        Learning priorities
      </h3>
      <p className="text-sm text-ink-muted">
        Ranked from your skill-gap results — no AI, no key needed. Required gaps first, direct
        misses before partial evidence.
      </p>
      <Button type="button" variant="ghost" size="sm" onClick={() => void generate()} disabled={status === "loading"}>
        {status === "loading" ? <Loader2 aria-hidden className="animate-spin" /> : <ListChecks aria-hidden />}
        {status === "loading" ? "Ranking…" : "Show learning priorities"}
      </Button>

      {status === "error" && error ? (
        <Alert variant="danger">
          <AlertTitle className="flex items-center gap-2">
            <AlertCircle aria-hidden className="size-4" />
            Something went wrong
          </AlertTitle>
          <p className="text-ink-muted">{error}</p>
        </Alert>
      ) : null}

      {result && result.priorities.length === 0 ? (
        <p className="text-sm text-ink-muted">
          No gaps found - this resume already covers the job&apos;s stated requirements.
        </p>
      ) : null}

      {result && result.priorities.length > 0 ? (
        <ol className="space-y-2">
          {result.priorities.map((priority, index) => (
            <li
              key={`${priority.skill}-${priority.requirement_text}`}
              className="space-y-1 rounded-card border border-border-strong bg-surface p-3 text-sm"
            >
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-ink-subtle">#{index + 1}</span>
                <span className="font-medium text-ink">{priority.skill}</span>
                <Badge variant={priority.importance === "required" ? "accent" : "neutral"}>
                  {priority.importance}
                </Badge>
                <Badge variant="neutral">{BUCKET_LABEL[priority.bucket] ?? priority.bucket}</Badge>
              </div>
              <p className="text-ink-muted">{priority.reason}</p>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

export function CareerPanel({
  documentId,
  versionId,
  sessionId,
  jobId,
}: {
  documentId: string;
  versionId: string | null;
  sessionId: string;
  jobId: string;
}) {
  return (
    <SectionCard description="Grounded in your resume and the job you already matched against - nothing is generated automatically, every action here is something you explicitly trigger.">
      <div className="grid gap-4 lg:grid-cols-2">
        <CoverLetterCard documentId={documentId} versionId={versionId} sessionId={sessionId} jobId={jobId} />
        <InterviewPrepCard documentId={documentId} versionId={versionId} sessionId={sessionId} jobId={jobId} />
        <div className="lg:col-span-2">
          <LearningPrioritiesCard
            documentId={documentId}
            versionId={versionId}
            sessionId={sessionId}
            jobId={jobId}
          />
        </div>
      </div>
    </SectionCard>
  );
}
