"use client";

import * as React from "react";
import { AlertCircle, FileText, Loader2, RotateCcw, Sparkles, Upload } from "lucide-react";

import { HealthReport } from "@/components/analysis/health-report";
import { ResumeBuilder } from "@/components/builder/resume-builder";
import { JobMatchPanel } from "@/components/matching/job-match-panel";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  api,
  type DocumentUploadResponse,
  type ResumeHealthResult,
} from "@/lib/api-client";

/*
  Upload -> analyze flow.

  A deliberately small state machine kept in one component rather than spread across the
  session store: this flow's state (which file, which document, which result) is not something
  any other part of the app needs to react to, so it does not belong in global state
  (PRIVACY_ARCHITECTURE.md section 4 - state stays in memory regardless, this is just about
  where).
*/

const ACCEPTED_EXTENSIONS = ".pdf,.docx,.txt";

type Status = "idle" | "uploading" | "uploaded" | "analyzing" | "analyzed" | "error";

export function ResumeAnalyzer({ sessionId }: { sessionId: string }) {
  const [status, setStatus] = React.useState<Status>("idle");
  const [fileName, setFileName] = React.useState<string | null>(null);
  const [upload, setUpload] = React.useState<DocumentUploadResponse | null>(null);
  const [result, setResult] = React.useState<ResumeHealthResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const reset = () => {
    setStatus("idle");
    setFileName(null);
    setUpload(null);
    setResult(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const handleFile = async (file: File) => {
    setFileName(file.name);
    setStatus("uploading");
    setError(null);
    try {
      const response = await api.uploadDocument(file, "resume", sessionId);
      setUpload(response);
      setStatus("uploaded");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload that file.");
      setStatus("error");
    }
  };

  const runAnalysis = async () => {
    if (!upload) return;
    setStatus("analyzing");
    setError(null);
    try {
      const health = await api.analyzeResume(upload.document_id, sessionId);
      setResult(health);
      setStatus("analyzed");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not analyze this resume.");
      setStatus("error");
    }
  };

  const onInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void handleFile(file);
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  };

  if (status === "analyzed" && result && upload) {
    return (
      <div className="space-y-8">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-2 text-sm text-ink-muted">
              <FileText aria-hidden className="size-4" />
              {fileName}
            </p>
            <Button variant="ghost" size="sm" onClick={reset}>
              <RotateCcw aria-hidden />
              Analyze a different resume
            </Button>
          </div>
          <HealthReport result={result} />
        </div>

        <div>
          <h3 className="text-lg font-semibold text-ink">Match against a job</h3>
          <p className="mt-1 text-sm text-ink-muted">
            Optional - see how this resume scores against a specific role.
          </p>
          <div className="mt-4">
            <JobMatchPanel documentId={upload.document_id} sessionId={sessionId} />
          </div>
        </div>

        <div>
          <h3 className="text-lg font-semibold text-ink">Resume builder</h3>
          <p className="mt-1 text-sm text-ink-muted">
            Edit your resume section by section, tailor it to a job with reviewable AI proposals,
            and export the result - every save creates a new version, so nothing is ever lost.
          </p>
          <div className="mt-4">
            <ResumeBuilder documentId={upload.document_id} sessionId={sessionId} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <Card>
      <CardContent className="p-6">
        {status === "idle" || status === "error" ? (
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={onDrop}
            className="flex flex-col items-center gap-3 rounded-card border-2 border-dashed border-border-strong px-6 py-10 text-center"
          >
            <Upload aria-hidden className="size-8 text-ink-subtle" />
            <div>
              <p className="font-medium text-ink">Upload your resume</p>
              <p className="text-sm text-ink-subtle">PDF, DOCX or TXT, up to 10 MB</p>
            </div>
            <Button asChild variant="secondary">
              <label htmlFor="resume-upload" className="cursor-pointer">
                Choose file
              </label>
            </Button>
            <input
              ref={inputRef}
              id="resume-upload"
              type="file"
              accept={ACCEPTED_EXTENSIONS}
              className="sr-only"
              onChange={onInputChange}
            />
            {status === "error" && error ? (
              <Alert variant="danger" className="mt-2 w-full max-w-md text-left">
                <AlertTitle className="flex items-center gap-2">
                  <AlertCircle aria-hidden className="size-4" />
                  Upload failed
                </AlertTitle>
                <p className="text-ink-muted">{error}</p>
              </Alert>
            ) : null}
          </div>
        ) : null}

        {status === "uploading" ? (
          <div className="space-y-3" aria-busy="true" aria-live="polite">
            <span className="sr-only">Uploading {fileName}</span>
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : null}

        {status === "uploaded" && upload ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <FileText aria-hidden className="size-4 text-ink-subtle" />
              <span className="font-medium text-ink">{fileName}</span>
              {upload.cached ? <Badge variant="neutral">Already processed</Badge> : null}
            </div>

            {upload.resume_summary ? (
              <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
                <SummaryStat label="Experience entries" value={upload.resume_summary.experience_entries} />
                <SummaryStat label="Education entries" value={upload.resume_summary.education_entries} />
                <SummaryStat label="Skill groups" value={upload.resume_summary.skill_groups} />
                <SummaryStat label="Projects" value={upload.resume_summary.project_entries} />
                <SummaryStat
                  label="Certifications"
                  value={upload.resume_summary.certification_entries}
                />
                <SummaryStat
                  label="Contact detected"
                  value={upload.resume_summary.has_email ? "Yes" : "No"}
                />
              </dl>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void runAnalysis()}>
                <Sparkles aria-hidden />
                Analyze resume health
              </Button>
              <Button variant="ghost" onClick={reset}>
                Choose a different file
              </Button>
            </div>
          </div>
        ) : null}

        {status === "analyzing" ? (
          <div
            className="flex flex-col items-center gap-3 py-10 text-center"
            aria-busy="true"
            aria-live="polite"
          >
            <Loader2 aria-hidden className="size-6 animate-spin text-ink-subtle" />
            <p className="text-sm text-ink-muted">Analyzing {fileName}…</p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function SummaryStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <dt className="text-ink-subtle">{label}</dt>
      <dd className="font-medium text-ink">{value}</dd>
    </div>
  );
}

