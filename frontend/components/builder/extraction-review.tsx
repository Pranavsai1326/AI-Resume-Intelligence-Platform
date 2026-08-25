"use client";

import * as React from "react";
import { CheckCircle2, ChevronDown, ChevronUp } from "lucide-react";

import { ResumePreview } from "@/components/builder/resume-preview";
import { SectionEditor } from "@/components/builder/section-editor";
import { Button } from "@/components/ui/button";
import { ApiError, api, type Resume, type ResumeVersion } from "@/lib/api-client";

/*
  Extraction review (Phase 9D) - the mandatory confirmation boundary between upload and every
  downstream feature. Built entirely on the existing SectionEditor/resume-edit.ts machinery
  (moveEntryToSection, DateRangeEditor, CustomSectionsEditor, ConfidenceHint) rather than a new
  editing paradigm; this component adds the surrounding review chrome: the one-line orientation
  note, the read-only "view original extraction" disclosure (reusing the version already created
  at upload time - no second persistent copy), and the explicit "Confirm resume & continue"
  action that unlocks the rest of the workspace.
*/

export function ExtractionReview({
  documentId,
  sessionId,
  resume,
  originalVersionId,
  onChange,
  onConfirm,
  confirming,
}: {
  documentId: string;
  sessionId: string;
  resume: Resume;
  originalVersionId: string | null;
  onChange: (next: Resume) => void;
  onConfirm: () => void;
  confirming: boolean;
}) {
  const [showOriginal, setShowOriginal] = React.useState(false);
  const [original, setOriginal] = React.useState<ResumeVersion | null>(null);
  const [loadingOriginal, setLoadingOriginal] = React.useState(false);
  const [originalError, setOriginalError] = React.useState<string | null>(null);

  const toggleOriginal = async () => {
    if (showOriginal) {
      setShowOriginal(false);
      return;
    }
    setShowOriginal(true);
    if (original || !originalVersionId) return;
    setLoadingOriginal(true);
    setOriginalError(null);
    try {
      const version = await api.getResumeVersion(originalVersionId, sessionId);
      setOriginal(version);
    } catch (err) {
      setOriginalError(
        err instanceof ApiError ? err.message : "Could not load the original extraction.",
      );
    } finally {
      setLoadingOriginal(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--text-h1)] font-semibold text-ink">Review your resume</h1>
          <p className="mt-1 text-sm text-ink-muted">
            We&apos;ve done our best reading this — fix anything that&apos;s wrong before
            continuing. A field marked{" "}
            <span className="font-medium text-warning">Check this</span> is one we&apos;re less
            sure about.
          </p>
        </div>
        {originalVersionId ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => void toggleOriginal()}>
            {showOriginal ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}
            {showOriginal ? "Hide original extraction" : "View original extraction"}
          </Button>
        ) : null}
      </div>

      {showOriginal ? (
        <div className="rounded-card border border-border bg-surface-muted p-4">
          {loadingOriginal ? (
            <p className="text-sm text-ink-subtle">Loading…</p>
          ) : originalError ? (
            <p className="text-sm text-danger">{originalError}</p>
          ) : original ? (
            <div className="max-h-96 overflow-y-auto">
              <ResumePreview resume={original.resume} />
            </div>
          ) : null}
        </div>
      ) : null}

      <SectionEditor documentId={documentId} sessionId={sessionId} resume={resume} onChange={onChange} />

      <div className="sticky bottom-0 -mx-4 border-t border-border bg-canvas/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <Button type="button" onClick={onConfirm} disabled={confirming}>
          <CheckCircle2 aria-hidden />
          {confirming ? "Confirming…" : "Confirm resume & continue"}
        </Button>
      </div>
    </div>
  );
}
