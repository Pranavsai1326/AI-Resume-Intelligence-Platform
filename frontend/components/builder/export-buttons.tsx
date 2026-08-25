"use client";

import * as React from "react";
import { AlertCircle, Download, Loader2 } from "lucide-react";

import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, api, type ExportFormat } from "@/lib/api-client";

/**
 * Triggers a real browser download using the filename the server derived
 * (`_safe_filename` in app/api/v1/export.py) from the Content-Disposition header.
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function ExportButtons({
  documentId,
  versionId,
  sessionId,
}: {
  documentId: string;
  versionId: string | null;
  sessionId: string;
}) {
  const [pending, setPending] = React.useState<ExportFormat | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const run = async (format: ExportFormat) => {
    setPending(format);
    setError(null);
    try {
      const { blob, filename } = await api.exportResume(documentId, format, sessionId, versionId);
      downloadBlob(blob, filename);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : `Could not export as ${format.toUpperCase()}. Please try again.`,
      );
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="secondary"
          onClick={() => void run("pdf")}
          disabled={pending !== null}
        >
          {pending === "pdf" ? <Loader2 aria-hidden className="animate-spin" /> : <Download aria-hidden />}
          Export PDF
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => void run("docx")}
          disabled={pending !== null}
        >
          {pending === "docx" ? (
            <Loader2 aria-hidden className="animate-spin" />
          ) : (
            <Download aria-hidden />
          )}
          Export DOCX
        </Button>
      </div>
      {error ? (
        <Alert variant="danger">
          <AlertTitle className="flex items-center gap-2">
            <AlertCircle aria-hidden className="size-4" />
            Export failed
          </AlertTitle>
          <p className="text-ink-muted">{error}</p>
        </Alert>
      ) : null}
    </div>
  );
}
