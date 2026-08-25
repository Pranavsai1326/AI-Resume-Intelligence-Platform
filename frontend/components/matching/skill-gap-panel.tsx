import { CheckCircle2, CircleDashed, CircleHelp, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { SkillGapBucket, SkillGapResult } from "@/lib/api-client";

/*
  Skill gap breakdown (PRD section 22): Strong / Moderate / Missing / Insufficient-evidence,
  grouped and explained rather than a flat list - the bucket itself is the headline, the resume-
  specific evidence sentence is the detail.
*/

const BUCKET_ORDER: SkillGapBucket[] = ["missing", "insufficient_evidence", "moderate", "strong"];

const BUCKET_META: Record<
  SkillGapBucket,
  { label: string; icon: React.ComponentType<{ className?: string }>; className: string }
> = {
  strong: { label: "Strong", icon: CheckCircle2, className: "text-success" },
  moderate: { label: "Moderate", icon: CircleDashed, className: "text-ink-muted" },
  missing: { label: "Missing", icon: XCircle, className: "text-danger" },
  insufficient_evidence: {
    label: "Worth confirming",
    icon: CircleHelp,
    className: "text-warning",
  },
};

export function SkillGapPanel({ result }: { result: SkillGapResult }) {
  if (result.entries.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Skill Gaps</CardTitle>
        <p className="text-sm text-ink-muted">
          {result.semantic_available
            ? "Includes skills that aren't an exact match but are plausibly covered by something you listed."
            : "Exact-match only on this deployment - semantic matching is not configured, so nothing is marked “worth confirming.”"}
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        {BUCKET_ORDER.map((bucket) => {
          const entries = result.entries.filter((e) => e.bucket === bucket);
          if (entries.length === 0) return null;
          const meta = BUCKET_META[bucket];
          return (
            <div key={bucket}>
              <h4 className={cn("flex items-center gap-2 text-sm font-semibold", meta.className)}>
                <meta.icon aria-hidden className="size-4" />
                {meta.label} ({entries.length})
              </h4>
              <ul className="mt-2 space-y-2">
                {entries.map((entry) => (
                  <li key={entry.skill} className="text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink">{entry.skill}</span>
                      <Badge variant={entry.importance === "required" ? "accent" : "neutral"}>
                        {entry.importance}
                      </Badge>
                    </div>
                    <p className="text-ink-subtle">{entry.evidence}</p>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
