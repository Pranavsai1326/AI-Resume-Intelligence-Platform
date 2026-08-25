"use client";

import * as React from "react";
import { AlertCircle, ListChecks, Loader2, Upload, Users } from "lucide-react";

import { CandidateDetail } from "@/components/screening/candidate-detail";
import { CandidateRankingList } from "@/components/screening/candidate-ranking-list";
import { ComparisonMatrix } from "@/components/screening/comparison-matrix";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  api,
  type CandidateResult,
  type ComparisonResult,
  type ScreeningContext,
  type ScreeningStatusSummary,
} from "@/lib/api-client";

/*
  Recruiter screening (Phase 7): paste a job description once, upload a candidate batch, watch it
  process asynchronously (app.queue.inprocess - genuinely running in the background, not
  simulated), then rank, open, compare and shortlist. Bulk upload and status polling are the only
  genuinely async pieces here; everything downstream (ranking, comparison) reads results already
  computed and stored server-side.
*/

const MIN_JD_LENGTH = 20;
const POLL_INTERVAL_MS = 1200;

type Phase = "idle" | "creating" | "ready" | "error";

export function ScreeningWorkspace({ sessionId }: { sessionId: string }) {
  const [phase, setPhase] = React.useState<Phase>("idle");
  const [jdText, setJdText] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const [screening, setScreening] = React.useState<ScreeningContext | null>(null);
  const [statusSummary, setStatusSummary] = React.useState<ScreeningStatusSummary | null>(null);
  const [candidates, setCandidates] = React.useState<CandidateResult[]>([]);
  const [uploading, setUploading] = React.useState(false);

  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [comparison, setComparison] = React.useState<ComparisonResult | null>(null);
  const [openCandidateId, setOpenCandidateId] = React.useState<string | null>(null);

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const inFlight = statusSummary
    ? statusSummary.pending + statusSummary.processing > 0
    : false;

  const refreshRanking = React.useCallback(
    async (screeningId: string) => {
      const page = await api.getScreeningRanking(screeningId, sessionId);
      setCandidates(page.candidates);
    },
    [sessionId],
  );

  React.useEffect(() => {
    if (!screening || !inFlight) return;
    const timer = setInterval(() => {
      void (async () => {
        try {
          const summary = await api.getScreeningStatus(screening.screening_id, sessionId);
          setStatusSummary(summary);
          await refreshRanking(screening.screening_id);
        } catch {
          // Transient poll failure - the interval retries on its own schedule.
        }
      })();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [screening, inFlight, sessionId, refreshRanking]);

  const startScreening = async () => {
    setPhase("creating");
    setError(null);
    try {
      const { job_id } = await api.createJobFromText(jdText, sessionId);
      const context = await api.createScreening(job_id, sessionId);
      setScreening(context);
      setPhase("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not read that job description.");
      setPhase("error");
    }
  };

  const onFilesChosen = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!screening || !files || files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadCandidates(screening.screening_id, Array.from(files), sessionId);
      const summary = await api.getScreeningStatus(screening.screening_id, sessionId);
      setStatusSummary(summary);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload those resumes.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const toggleSelect = (candidateId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(candidateId)) next.delete(candidateId);
      else next.add(candidateId);
      return next;
    });
    setComparison(null);
  };

  const runComparison = async () => {
    if (!screening || selected.size < 2) return;
    try {
      const result = await api.compareCandidates(
        screening.screening_id,
        Array.from(selected),
        sessionId,
      );
      setComparison(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not compare those candidates.");
    }
  };

  const onShortlistChange = (updated: CandidateResult) => {
    setCandidates((prev) =>
      prev.map((c) => (c.candidate_id === updated.candidate_id ? updated : c)),
    );
  };

  const openCandidate = candidates.find((c) => c.candidate_id === openCandidateId) ?? null;

  if (openCandidate && screening) {
    return (
      <CandidateDetail
        screeningId={screening.screening_id}
        sessionId={sessionId}
        candidate={openCandidate}
        onClose={() => setOpenCandidateId(null)}
        onShortlistChange={onShortlistChange}
      />
    );
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users aria-hidden className="size-4 text-accent" />
            Start a screening
          </CardTitle>
          <p className="text-sm text-ink-muted">
            Paste the job description once, then upload a candidate batch below.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            rows={5}
            placeholder="Paste the job posting, including a Requirements section..."
            className="w-full rounded-card border border-border-strong bg-surface p-3 text-sm text-ink placeholder:text-ink-subtle focus-visible:outline-none"
            disabled={phase === "creating" || screening !== null}
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
          {!screening ? (
            <Button
              type="button"
              onClick={() => void startScreening()}
              disabled={jdText.trim().length < MIN_JD_LENGTH || phase === "creating"}
            >
              {phase === "creating" ? (
                <Loader2 aria-hidden className="animate-spin" />
              ) : (
                <ListChecks aria-hidden />
              )}
              {phase === "creating" ? "Starting…" : "Start screening"}
            </Button>
          ) : (
            <Badge variant="success">Screening started</Badge>
          )}
        </CardContent>
      </Card>

      {screening ? (
        <Card>
          <CardHeader>
            <CardTitle>Upload candidates</CardTitle>
            <p className="text-sm text-ink-muted">
              PDF, DOCX or TXT, up to 100 resumes per screening. Each is processed in the
              background and validated, redacted, and scored independently.
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button asChild variant="secondary" disabled={uploading}>
              <label htmlFor="candidate-upload" className="cursor-pointer">
                {uploading ? (
                  <Loader2 aria-hidden className="animate-spin" />
                ) : (
                  <Upload aria-hidden />
                )}
                {uploading ? "Uploading…" : "Choose resumes"}
              </label>
            </Button>
            <input
              ref={fileInputRef}
              id="candidate-upload"
              type="file"
              accept=".pdf,.docx,.txt"
              multiple
              className="sr-only"
              onChange={(e) => void onFilesChosen(e)}
            />

            {statusSummary ? (
              <div className="flex flex-wrap gap-2 text-sm">
                <Badge variant="neutral">{statusSummary.total} total</Badge>
                <Badge variant={inFlight ? "warning" : "neutral"}>
                  {statusSummary.pending + statusSummary.processing} processing
                </Badge>
                <Badge variant="success">{statusSummary.completed} completed</Badge>
                {statusSummary.failed > 0 ? (
                  <Badge variant="danger">{statusSummary.failed} failed</Badge>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {screening && candidates.length > 0 ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-ink">Ranking</h3>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void runComparison()}
              disabled={selected.size < 2}
            >
              Compare {selected.size > 0 ? `(${selected.size})` : ""}
            </Button>
          </div>
          <CandidateRankingList
            candidates={candidates}
            selected={selected}
            onToggleSelect={toggleSelect}
            onOpen={setOpenCandidateId}
          />
          {comparison ? <ComparisonMatrix result={comparison} /> : null}
        </div>
      ) : null}
    </div>
  );
}
