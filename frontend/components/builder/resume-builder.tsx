"use client";

import * as React from "react";
import { AlertCircle, Loader2, Save } from "lucide-react";

import { CareerPanel } from "@/components/builder/career-panel";
import { ExportButtons } from "@/components/builder/export-buttons";
import { ResumePreview } from "@/components/builder/resume-preview";
import { SectionEditor } from "@/components/builder/section-editor";
import { TailorPanel } from "@/components/builder/tailor-panel";
import { VersionSwitcher } from "@/components/builder/version-switcher";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api, type Resume, type ResumeVersion, type VersionSummary } from "@/lib/api-client";

/*
  Resume Builder (Phase 5, PRD section 19-22): edit a structured resume, see it live, switch
  between versions, tailor it to a job with reviewable proposals, and export it. Every meaningful
  change becomes a new immutable version rather than mutating one in place - the builder never
  calls the versions API with a PUT/PATCH because there isn't one, by design.
*/

export function ResumeBuilder({ documentId, sessionId }: { documentId: string; sessionId: string }) {
  const [status, setStatus] = React.useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = React.useState<string | null>(null);
  const [versions, setVersions] = React.useState<VersionSummary[]>([]);
  const [currentVersionId, setCurrentVersionId] = React.useState<string | null>(null);
  const [resume, setResume] = React.useState<Resume | null>(null);
  const [dirty, setDirty] = React.useState(false);
  const [saving, setSaving] = React.useState(false);

  const loadVersion = React.useCallback(
    async (versionId: string) => {
      const version = await api.getResumeVersion(versionId, sessionId);
      setCurrentVersionId(version.version_id);
      setResume(version.resume);
      setDirty(false);
    },
    [sessionId],
  );

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setStatus("loading");
      setError(null);
      try {
        const list = await api.listResumeVersions(documentId, sessionId);
        if (cancelled) return;
        setVersions(list);
        const latest = list[list.length - 1];
        if (latest) await loadVersion(latest.version_id);
        setStatus("ready");
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load the resume builder.");
        setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, sessionId]);

  const refreshVersions = async (): Promise<VersionSummary[]> => {
    const list = await api.listResumeVersions(documentId, sessionId);
    setVersions(list);
    return list;
  };

  const onSelectVersion = (versionId: string) => {
    void loadVersion(versionId);
  };

  const onChangeResume = (next: Resume) => {
    setResume(next);
    setDirty(true);
  };

  const saveVersion = async () => {
    if (!resume) return;
    setSaving(true);
    setError(null);
    try {
      const version = await api.saveResumeVersion(
        {
          documentId,
          label: `Edit ${new Date().toLocaleTimeString()}`,
          resume,
          basedOnVersionId: currentVersionId,
          source: "manual_edit",
        },
        sessionId,
      );
      await refreshVersions();
      setCurrentVersionId(version.version_id);
      setDirty(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save this version.");
    } finally {
      setSaving(false);
    }
  };

  const onTailorApplied = async (version: ResumeVersion) => {
    await refreshVersions();
    setCurrentVersionId(version.version_id);
    setResume(version.resume);
    setDirty(false);
  };

  if (status === "loading") {
    return (
      <div className="space-y-3" aria-busy="true" aria-live="polite">
        <span className="sr-only">Loading the resume builder</span>
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <Alert variant="danger">
        <AlertTitle className="flex items-center gap-2">
          <AlertCircle aria-hidden className="size-4" />
          Could not load the resume builder
        </AlertTitle>
        <p className="text-ink-muted">{error}</p>
      </Alert>
    );
  }

  if (!resume) return null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button type="button" onClick={() => void saveVersion()} disabled={!dirty || saving}>
            {saving ? <Loader2 aria-hidden className="animate-spin" /> : <Save aria-hidden />}
            {saving ? "Saving…" : dirty ? "Save as new version" : "Saved"}
          </Button>
          <ExportButtons documentId={documentId} versionId={currentVersionId} sessionId={sessionId} />
        </div>
      </div>

      {error ? (
        <Alert variant="danger">
          <AlertTitle className="flex items-center gap-2">
            <AlertCircle aria-hidden className="size-4" />
            Something went wrong
          </AlertTitle>
          <p className="text-ink-muted">{error}</p>
        </Alert>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[220px_1fr_1fr]">
        <div className="lg:order-1">
          <VersionSwitcher
            versions={versions}
            currentVersionId={currentVersionId}
            onSelect={onSelectVersion}
          />
        </div>
        <div className="lg:order-2">
          <SectionEditor
            documentId={documentId}
            sessionId={sessionId}
            resume={resume}
            onChange={onChangeResume}
          />
        </div>
        <div className="lg:order-3 lg:sticky lg:top-4 lg:self-start">
          <ResumePreview resume={resume} />
        </div>
      </div>

      <TailorPanel
        documentId={documentId}
        versionId={currentVersionId}
        sessionId={sessionId}
        onApplied={onTailorApplied}
      />

      <CareerPanel documentId={documentId} versionId={currentVersionId} sessionId={sessionId} />
    </div>
  );
}
