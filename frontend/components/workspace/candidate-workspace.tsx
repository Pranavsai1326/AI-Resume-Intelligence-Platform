"use client";

import * as React from "react";
import { AlertCircle, FileText, Loader2, RotateCcw, Sparkles, Upload } from "lucide-react";

import { CareerPanel } from "@/components/builder/career-panel";
import { ExportButtons } from "@/components/builder/export-buttons";
import { ExtractionReview } from "@/components/builder/extraction-review";
import { ResumePreview } from "@/components/builder/resume-preview";
import { SectionEditor } from "@/components/builder/section-editor";
import { TailorPanel } from "@/components/builder/tailor-panel";
import { VersionSwitcher } from "@/components/builder/version-switcher";
import { HealthReport } from "@/components/analysis/health-report";
import { JobMatchReport } from "@/components/matching/job-match-report";
import { SkillGapPanel } from "@/components/matching/skill-gap-panel";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ProgressRail, type RailStep } from "@/components/ui/progress-rail";
import { SectionCard } from "@/components/ui/section-card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  api,
  type DocumentUploadResponse,
  type JobMatchResult,
  type Resume,
  type ResumeVersion,
  type VersionSummary,
} from "@/lib/api-client";

/*
  Candidate journey (Phase 9D + 9E): Upload -> Review -> Confirm -> Health -> Match -> Gaps ->
  Improve -> Career AI -> Export, driven by ProgressRail. Not a wizard: every reachable step stays
  directly clickable, and a step is only gated by whether its actual data dependency exists (a
  resume, a confirmation, a match) - never by "have you visited the previous step yet".
*/

type StepKey = "upload" | "review" | "health" | "match" | "gaps" | "improve" | "career" | "export";

const STEP_LABEL: Record<StepKey, string> = {
  upload: "Upload",
  review: "Review",
  health: "Health",
  match: "Match",
  gaps: "Gaps",
  improve: "Improve",
  career: "Career AI",
  export: "Export",
};

const ACCEPTED_EXTENSIONS = ".pdf,.docx,.txt";

export function CandidateWorkspace({ sessionId }: { sessionId: string }) {
  const [fileName, setFileName] = React.useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = React.useState<"idle" | "uploading" | "error">("idle");
  const [uploadError, setUploadError] = React.useState<string | null>(null);
  const [upload, setUpload] = React.useState<DocumentUploadResponse | null>(null);

  const [versions, setVersions] = React.useState<VersionSummary[]>([]);
  const [currentVersionId, setCurrentVersionId] = React.useState<string | null>(null);
  const [originalVersionId, setOriginalVersionId] = React.useState<string | null>(null);
  const [resume, setResume] = React.useState<Resume | null>(null);
  const [resumeDirty, setResumeDirty] = React.useState(false);
  const [loadingResume, setLoadingResume] = React.useState(false);

  const [confirmed, setConfirmed] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);

  const [health, setHealth] = React.useState<import("@/lib/api-client").ResumeHealthResult | null>(null);
  const [loadingHealth, setLoadingHealth] = React.useState(false);

  const [jobId, setJobId] = React.useState<string | null>(null);
  const [jdText, setJdText] = React.useState("");
  const [match, setMatch] = React.useState<JobMatchResult | null>(null);
  const [matching, setMatching] = React.useState(false);
  const [matchError, setMatchError] = React.useState<string | null>(null);

  const [step, setStep] = React.useState<StepKey>("upload");

  const loadVersion = React.useCallback(
    async (versionId: string) => {
      setLoadingResume(true);
      try {
        const version = await api.getResumeVersion(versionId, sessionId);
        setCurrentVersionId(version.version_id);
        setResume(version.resume);
        setResumeDirty(false);
      } finally {
        setLoadingResume(false);
      }
    },
    [sessionId],
  );

  const loadVersions = React.useCallback(
    async (documentId: string) => {
      const list = await api.listResumeVersions(documentId, sessionId);
      setVersions(list);
      const first = list[0];
      const latest = list[list.length - 1];
      if (first) setOriginalVersionId(first.version_id);
      if (latest) await loadVersion(latest.version_id);
    },
    [sessionId, loadVersion],
  );

  const handleFile = async (file: File) => {
    setFileName(file.name);
    setUploadStatus("uploading");
    setUploadError(null);
    try {
      const response = await api.uploadDocument(file, "resume", sessionId);
      setUpload(response);
      await loadVersions(response.document_id);
      setUploadStatus("idle");
      setStep("review");
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Could not upload that file.");
      setUploadStatus("error");
    }
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  };

  const onInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void handleFile(file);
  };

  const onChangeResume = (next: Resume) => {
    setResume(next);
    setResumeDirty(true);
  };

  const saveResumeVersion = async (source: "manual_edit" = "manual_edit"): Promise<ResumeVersion | null> => {
    if (!resume || !upload) return null;
    const version = await api.saveResumeVersion(
      {
        documentId: upload.document_id,
        label: `Edit ${new Date().toLocaleTimeString()}`,
        resume,
        basedOnVersionId: currentVersionId,
        source,
      },
      sessionId,
    );
    const list = await api.listResumeVersions(upload.document_id, sessionId);
    setVersions(list);
    setCurrentVersionId(version.version_id);
    setResumeDirty(false);
    return version;
  };

  const onConfirm = async () => {
    setConfirming(true);
    try {
      await saveResumeVersion();
      setConfirmed(true);
      setStep("health");
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Could not save your changes.");
    } finally {
      setConfirming(false);
    }
  };

  const runHealth = React.useCallback(async () => {
    if (!upload) return;
    setLoadingHealth(true);
    try {
      const result = await api.analyzeResume(upload.document_id, sessionId);
      setHealth(result);
    } catch {
      // Surfaced via the Health section itself on next render if it stays null.
    } finally {
      setLoadingHealth(false);
    }
  }, [upload, sessionId]);

  React.useEffect(() => {
    if (step === "health" && confirmed && !health && !loadingHealth) void runHealth();
  }, [step, confirmed, health, loadingHealth, runHealth]);

  const runMatch = async () => {
    if (!upload) return;
    setMatching(true);
    setMatchError(null);
    try {
      const { job_id } = await api.createJobFromText(jdText, sessionId);
      setJobId(job_id);
      const result = await api.matchResumeToJob(upload.document_id, job_id, sessionId);
      setMatch(result);
    } catch (err) {
      setMatchError(err instanceof ApiError ? err.message : "Could not match against this job description.");
    } finally {
      setMatching(false);
    }
  };

  const onTailorApplied = async (version: ResumeVersion) => {
    const list = await api.listResumeVersions(upload!.document_id, sessionId);
    setVersions(list);
    setCurrentVersionId(version.version_id);
    setResume(version.resume);
    setResumeDirty(false);
  };

  const steps: RailStep[] = [
    { key: "upload", label: STEP_LABEL.upload, reachable: true, complete: Boolean(upload) },
    { key: "review", label: STEP_LABEL.review, reachable: Boolean(upload), complete: confirmed },
    {
      key: "health",
      label: STEP_LABEL.health,
      reachable: confirmed,
      reason: "Confirm your resume first.",
    },
    { key: "match", label: STEP_LABEL.match, reachable: confirmed, reason: "Confirm your resume first." },
    {
      key: "gaps",
      label: STEP_LABEL.gaps,
      reachable: confirmed && Boolean(match),
      reason: match ? undefined : "Run a job match first.",
    },
    { key: "improve", label: STEP_LABEL.improve, reachable: confirmed, reason: "Confirm your resume first." },
    {
      key: "career",
      label: STEP_LABEL.career,
      reachable: confirmed && Boolean(match),
      reason: match ? undefined : "Run a job match first.",
    },
    { key: "export", label: STEP_LABEL.export, reachable: confirmed, reason: "Confirm your resume first." },
  ];

  return (
    <div className="space-y-6">
      <ProgressRail steps={steps} currentKey={step} onSelect={(key) => setStep(key as StepKey)} />

      {step === "upload" ? (
        <Card>
          <CardContent className="p-6">
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
                id="resume-upload"
                type="file"
                accept={ACCEPTED_EXTENSIONS}
                className="sr-only"
                onChange={onInputChange}
              />
              {uploadStatus === "uploading" ? (
                <p className="flex items-center gap-2 text-sm text-ink-muted" aria-live="polite">
                  <Loader2 aria-hidden className="size-4 animate-spin" />
                  Uploading {fileName}…
                </p>
              ) : null}
              {uploadStatus === "error" && uploadError ? (
                <Alert variant="danger" className="mt-2 w-full max-w-md text-left">
                  <AlertTitle className="flex items-center gap-2">
                    <AlertCircle aria-hidden className="size-4" />
                    Upload failed
                  </AlertTitle>
                  <p className="text-ink-muted">{uploadError}</p>
                </Alert>
              ) : null}
              {upload ? (
                <p className="mt-2 flex items-center gap-2 text-sm text-success">
                  <FileText aria-hidden className="size-4" />
                  {fileName} uploaded — review the extracted information before continuing.
                </p>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === "review" && upload ? (
        loadingResume || !resume ? (
          <Skeleton className="h-96" />
        ) : (
          <ExtractionReview
            documentId={upload.document_id}
            sessionId={sessionId}
            resume={resume}
            originalVersionId={originalVersionId}
            onChange={onChangeResume}
            onConfirm={() => void onConfirm()}
            confirming={confirming}
          />
        )
      ) : null}

      {step === "health" ? (
        <SectionCard title="Resume Health">
          {loadingHealth || !health ? (
            <Skeleton className="h-40" />
          ) : (
            <HealthReport result={health} />
          )}
        </SectionCard>
      ) : null}

      {step === "match" ? (
        <SectionCard
          title="Job Match"
          description="Paste a job description to see how this resume scores against it - required and preferred requirements, experience, education, and (where configured) semantic relevance."
        >
          <Card>
            <CardContent className="space-y-4 p-6">
              <textarea
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                rows={8}
                placeholder="Paste the full job posting, including a Requirements or Qualifications section..."
                className="w-full rounded-card border border-border-strong bg-surface p-3 text-sm text-ink placeholder:text-ink-subtle focus-visible:outline-none"
                disabled={matching}
              />
              {matchError ? (
                <Alert variant="danger">
                  <AlertTitle className="flex items-center gap-2">
                    <AlertCircle aria-hidden className="size-4" />
                    Could not compute a match
                  </AlertTitle>
                  <p className="text-ink-muted">{matchError}</p>
                </Alert>
              ) : null}
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => void runMatch()} disabled={jdText.trim().length < 20 || matching}>
                  {matching ? <Loader2 aria-hidden className="animate-spin" /> : <Sparkles aria-hidden />}
                  {matching ? "Matching…" : match ? "Match against this job instead" : "Match against this job"}
                </Button>
                {match ? (
                  <Button variant="ghost" size="sm" onClick={() => setMatch(null)}>
                    <RotateCcw aria-hidden />
                    Clear result
                  </Button>
                ) : null}
              </div>
            </CardContent>
          </Card>
          {match ? <JobMatchReport result={match} /> : null}
        </SectionCard>
      ) : null}

      {step === "gaps" ? (
        <SectionCard title="Skill Gaps">
          {match ? (
            <SkillGapPanel result={match.skill_gaps} onViewLearningPriorities={() => setStep("career")} />
          ) : (
            <EmptyMatchState onGoToMatch={() => setStep("match")} />
          )}
        </SectionCard>
      ) : null}

      {step === "improve" && resume && upload ? (
        <SectionCard title="Improve your resume">
          <div className="grid gap-5 lg:grid-cols-[220px_1fr_1fr]">
            <div className="lg:order-1">
              <VersionSwitcher
                versions={versions}
                currentVersionId={currentVersionId}
                onSelect={(id) => void loadVersion(id)}
              />
            </div>
            <div className="lg:order-2">
              <SectionEditor
                documentId={upload.document_id}
                sessionId={sessionId}
                resume={resume}
                onChange={onChangeResume}
              />
              <Button
                type="button"
                className="mt-4"
                onClick={() => void saveResumeVersion()}
                disabled={!resumeDirty}
              >
                {resumeDirty ? "Save as new version" : "Saved"}
              </Button>
            </div>
            <div className="lg:order-3 lg:sticky lg:top-4 lg:self-start">
              <ResumePreview resume={resume} />
            </div>
          </div>
          <TailorPanel
            documentId={upload.document_id}
            versionId={currentVersionId}
            sessionId={sessionId}
            onApplied={onTailorApplied}
          />
        </SectionCard>
      ) : null}

      {step === "career" ? (
        <SectionCard title="Career AI">
          {upload && jobId ? (
            <CareerPanel
              documentId={upload.document_id}
              versionId={currentVersionId}
              sessionId={sessionId}
              jobId={jobId}
            />
          ) : (
            <EmptyMatchState onGoToMatch={() => setStep("match")} label="Run a job match first to unlock Career AI." />
          )}
        </SectionCard>
      ) : null}

      {step === "export" && upload ? (
        <SectionCard title="Export">
          <div className="space-y-2">
            <p className="text-sm text-ink-muted">
              Exporting{" "}
              <span className="font-medium text-ink">
                {versions.find((v) => v.version_id === currentVersionId)?.label ?? "the current version"}
              </span>
              .
            </p>
            <ExportButtons documentId={upload.document_id} versionId={currentVersionId} sessionId={sessionId} />
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}

function EmptyMatchState({ onGoToMatch, label }: { onGoToMatch: () => void; label?: string }) {
  return (
    <div className="rounded-card border border-border bg-surface-muted p-4 text-sm text-ink-muted">
      <p>{label ?? "Run a job match first to see skill gaps."}</p>
      <Button type="button" variant="ghost" size="sm" onClick={onGoToMatch} className="mt-1 -ml-3">
        Go to Match
      </Button>
    </div>
  );
}
