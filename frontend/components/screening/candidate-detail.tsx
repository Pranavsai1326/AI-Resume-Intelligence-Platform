"use client";

import * as React from "react";
import { Loader2, Star, X } from "lucide-react";

import { ResumePreview } from "@/components/builder/resume-preview";
import { JobMatchReport } from "@/components/matching/job-match-report";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, api, type CandidateResult } from "@/lib/api-client";

/*
  One candidate's full explainable breakdown ("why ranked #N") - the same JobMatchReport used for
  a single candidate's own match view, reused here rather than duplicated, plus the redacted
  resume itself (ResumePreview already renders gracefully with no name - blind review by
  construction, not a display-time filter this view has to apply).
*/

export function CandidateDetail({
  screeningId,
  sessionId,
  candidate,
  onClose,
  onShortlistChange,
}: {
  screeningId: string;
  sessionId: string;
  candidate: CandidateResult;
  onClose: () => void;
  onShortlistChange: (updated: CandidateResult) => void;
}) {
  const [updating, setUpdating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const toggleShortlist = async () => {
    setUpdating(true);
    setError(null);
    try {
      const updated = await api.setShortlisted(
        screeningId,
        candidate.candidate_id,
        !candidate.shortlisted,
        sessionId,
      );
      onShortlistChange(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update shortlist status.");
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold text-ink">Candidate {candidate.candidate_id.slice(0, 8)}</h3>
          {candidate.redaction.applied ? (
            <Badge variant="neutral">Redacted: {candidate.redaction.fields.join(", ")}</Badge>
          ) : null}
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          <X aria-hidden />
          Close
        </Button>
      </div>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <Button
        type="button"
        variant={candidate.shortlisted ? "secondary" : "primary"}
        size="sm"
        onClick={() => void toggleShortlist()}
        disabled={updating}
      >
        {updating ? <Loader2 aria-hidden className="animate-spin" /> : <Star aria-hidden />}
        {candidate.shortlisted ? "Remove from shortlist" : "Add to shortlist"}
      </Button>

      <div className="grid gap-4 lg:grid-cols-2">
        <JobMatchReport result={candidate.match} />
        <ResumePreview resume={candidate.resume} />
      </div>
    </div>
  );
}
