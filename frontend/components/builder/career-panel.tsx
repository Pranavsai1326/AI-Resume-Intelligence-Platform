"use client";

import * as React from "react";
import {
  AlertCircle,
  AlertTriangle,
  BookOpen,
  Info,
  ListChecks,
  Loader2,
  Mail,
  MessagesSquare,
} from "lucide-react";

import { Alert, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  api,
  type CoverLetterProposal,
  type InterviewPrepProposal,
  type LearningPriorityResult,
} from "@/lib/api-client";

/*
  Phase 6 - career intelligence: cover letters and interview prep (Layer 3, honestly unavailable
  with no LLM key configured, every generated line fact-guarded against the resume and job) plus
  learning priorities (Layer 1, deterministic, needs no key at all - just Phase 4's skill gaps
  reordered into "what to learn next"). All three share one job description, entered once here
  rather than duplicating the paste-a-JD flow TailorPanel already has.
*/

const MIN_JD_LENGTH = 20;

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

function UnavailableNotice({ reason }: { reason: string | null }) {
  return (
    <div className="flex items-start gap-2 rounded-card border border-border bg-surface-muted p-3 text-sm text-ink-muted">
      <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-ink-subtle" />
      <p>{reason ?? "AI writing is not available right now."}</p>
    </div>
  );
}

function FactGuardFindings({ findings }: { findings: string[] }) {
  if (findings.length === 0) {
    return <Badge variant="success">No unsupported claims detected</Badge>;
  }
  return (
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
  );
}

function CoverLetterCard({
  documentId,
  versionId,
  sessionId,
  jobId,
}: {
  documentId: string;
  versionId: string | null;
  sessionId: string;
  jobId: string | null;
}) {
  const [status, setStatus] = React.useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = React.useState<CoverLetterProposal | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const generate = async () => {
    if (!jobId) return;
    setStatus("loading");
    setError(null);
    try {
      const proposal = await api.generateCoverLetter(documentId, jobId, sessionId, versionId);
      setResult(proposal);
      setStatus("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate a cover letter.");
      setStatus("error");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail aria-hidden className="size-4 text-accent" />
          Cover letter
        </CardTitle>
        <p className="text-sm text-ink-muted">
          Grounded in your resume and the job&apos;s stated requirements - never a fact it
          can&apos;t point back to.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button type="button" onClick={() => void generate()} disabled={!jobId || status === "loading"}>
          {status === "loading" ? <Loader2 aria-hidden className="animate-spin" /> : <Mail aria-hidden />}
          {status === "loading" ? "Writing…" : "Generate cover letter"}
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

        {result && !result.available ? <UnavailableNotice reason={result.unavailable_reason} /> : null}

        {result?.available ? (
          <div className="space-y-3 rounded-card border border-border-strong bg-surface p-3 text-sm">
            <p className="text-ink">{result.salutation}</p>
            {result.body_paragraphs.map((paragraph, index) => (
              <p key={index} className="text-ink-muted">
                {paragraph}
              </p>
            ))}
            <p className="text-ink">{result.closing}</p>
            <FactGuardFindings findings={result.fact_guard_findings} />
          </div>
        ) : null}
      </CardContent>
    </Card>
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
  jobId: string | null;
}) {
  const [status, setStatus] = React.useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = React.useState<InterviewPrepProposal | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const generate = async () => {
    if (!jobId) return;
    setStatus("loading");
    setError(null);
    try {
      const proposal = await api.generateInterviewQuestions(documentId, jobId, sessionId, versionId);
      setResult(proposal);
      setStatus("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate interview questions.");
      setStatus("error");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessagesSquare aria-hidden className="size-4 text-accent" />
          Interview prep
        </CardTitle>
        <p className="text-sm text-ink-muted">
          Questions traced to a specific line in your resume or the job posting, not a generic
          question bank.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button type="button" onClick={() => void generate()} disabled={!jobId || status === "loading"}>
          {status === "loading" ? (
            <Loader2 aria-hidden className="animate-spin" />
          ) : (
            <MessagesSquare aria-hidden />
          )}
          {status === "loading" ? "Preparing…" : "Generate interview questions"}
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

        {result && !result.available ? <UnavailableNotice reason={result.unavailable_reason} /> : null}

        {result?.available ? (
          <ul className="space-y-2">
            {result.questions.map((question) => (
              <li
                key={question.question}
                className="space-y-1.5 rounded-card border border-border-strong bg-surface p-3 text-sm"
              >
                <div className="flex items-center gap-2">
                  <Badge variant="accent">{CATEGORY_LABEL[question.category] ?? question.category}</Badge>
                </div>
                <p className="font-medium text-ink">{question.question}</p>
                <p className="text-ink-muted">{question.rationale}</p>
                <p className="text-xs text-ink-subtle">Grounded in: &quot;{question.grounded_in}&quot;</p>
                <FactGuardFindings findings={question.fact_guard_findings} />
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
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
  jobId: string | null;
}) {
  const [status, setStatus] = React.useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = React.useState<LearningPriorityResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const generate = async () => {
    if (!jobId) return;
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
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookOpen aria-hidden className="size-4 text-accent" />
          Learning priorities
        </CardTitle>
        <p className="text-sm text-ink-muted">
          Ranked from Phase 4&apos;s skill-gap analysis - no AI, no key needed. Required gaps
          first, the most direct misses before partial evidence.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button type="button" onClick={() => void generate()} disabled={!jobId || status === "loading"}>
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

        {result && !result.semantic_available && result.priorities.length > 0 ? (
          <p className="text-xs text-ink-subtle">
            Semantic matching is unavailable on this deployment, so some partial matches may show
            as flat misses rather than &quot;worth confirming&quot;.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function CareerPanel({
  documentId,
  versionId,
  sessionId,
}: {
  documentId: string;
  versionId: string | null;
  sessionId: string;
}) {
  const [jdText, setJdText] = React.useState("");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [creatingJob, setCreatingJob] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submitJobDescription = async () => {
    setCreatingJob(true);
    setError(null);
    try {
      const { job_id } = await api.createJobFromText(jdText, sessionId);
      setJobId(job_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not read that job description.");
    } finally {
      setCreatingJob(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Career intelligence</CardTitle>
          <p className="text-sm text-ink-muted">
            Paste a job description once to unlock a cover letter, interview prep, and learning
            priorities below.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            rows={5}
            placeholder="Paste the job posting, including a Requirements section..."
            className="w-full rounded-card border border-border-strong bg-surface p-3 text-sm text-ink placeholder:text-ink-subtle focus-visible:outline-none"
            disabled={creatingJob}
          />
          {error ? (
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
            onClick={() => void submitJobDescription()}
            disabled={jdText.trim().length < MIN_JD_LENGTH || creatingJob}
          >
            {creatingJob ? <Loader2 aria-hidden className="animate-spin" /> : <ListChecks aria-hidden />}
            {creatingJob ? "Reading…" : jobId ? "Use this job description instead" : "Use this job description"}
          </Button>
        </CardContent>
      </Card>

      {jobId ? (
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
      ) : null}
    </div>
  );
}
