"use client";

import * as React from "react";
import { AlertCircle, Loader2, RotateCcw, Target } from "lucide-react";

import { JobMatchReport } from "@/components/matching/job-match-report";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, api, type JobMatchResult } from "@/lib/api-client";

/*
  Paste a job description -> match it against the already-uploaded resume.

  A small state machine local to this panel, same reasoning as ResumeAnalyzer: this flow's state
  is not something the rest of the app needs to react to.
*/

type Status = "idle" | "matching" | "matched" | "error";

const MIN_JD_LENGTH = 20;

export function JobMatchPanel({ documentId, sessionId }: { documentId: string; sessionId: string }) {
  const [status, setStatus] = React.useState<Status>("idle");
  const [jdText, setJdText] = React.useState("");
  const [result, setResult] = React.useState<JobMatchResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const runMatch = async () => {
    setStatus("matching");
    setError(null);
    try {
      const { job_id } = await api.createJobFromText(jdText, sessionId);
      const match = await api.matchResumeToJob(documentId, job_id, sessionId);
      setResult(match);
      setStatus("matched");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not match against this job description.");
      setStatus("error");
    }
  };

  const reset = () => {
    setStatus("idle");
    setResult(null);
    setError(null);
    setJdText("");
  };

  if (status === "matched" && result) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={reset}>
          <RotateCcw aria-hidden />
          Try a different job description
        </Button>
        <JobMatchReport result={result} />
      </div>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div>
          <label htmlFor="jd-text" className="text-sm font-medium text-ink">
            Paste a job description
          </label>
          <p className="text-sm text-ink-subtle">
            Compared against the resume you just uploaded - required and preferred requirements,
            experience, education, and (where configured) semantic relevance.
          </p>
        </div>
        <textarea
          id="jd-text"
          value={jdText}
          onChange={(e) => setJdText(e.target.value)}
          rows={8}
          placeholder="Paste the full job posting, including a Requirements or Qualifications section..."
          className="w-full rounded-card border border-border-strong bg-surface p-3 text-sm text-ink placeholder:text-ink-subtle focus-visible:outline-none"
          disabled={status === "matching"}
        />
        {status === "error" && error ? (
          <Alert variant="danger">
            <AlertTitle className="flex items-center gap-2">
              <AlertCircle aria-hidden className="size-4" />
              Could not compute a match
            </AlertTitle>
            <p className="text-ink-muted">{error}</p>
          </Alert>
        ) : null}
        <Button
          onClick={() => void runMatch()}
          disabled={jdText.trim().length < MIN_JD_LENGTH || status === "matching"}
        >
          {status === "matching" ? (
            <Loader2 aria-hidden className="animate-spin" />
          ) : (
            <Target aria-hidden />
          )}
          {status === "matching" ? "Matching…" : "Match against this job"}
        </Button>
      </CardContent>
    </Card>
  );
}
