"use client";

import * as React from "react";
import { CheckCircle2, ChevronDown, Info, TriangleAlert } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreBar } from "@/components/analysis/score-bar";
import { cn } from "@/lib/utils";
import type { ComponentScore, Evidence, ResumeHealthResult } from "@/lib/api-client";

/*
  Resume Health report.

  Every score renders with the evidence that produced it - never a bare number (API.md,
  PRD section 13). Components render in a fixed, deliberate order rather than the object's
  iteration order, and start collapsed except the lowest-scoring one, so the reader's eye goes
  straight to what needs attention first.
*/

const COMPONENT_ORDER = [
  "ats_compatibility",
  "content_quality",
  "experience_quality",
  "skills_coverage",
  "formatting",
  "impact",
];

function overallBand(score: number): { label: string; className: string } {
  if (score >= 80) return { label: "Strong", className: "text-success" };
  if (score >= 50) return { label: "Needs work", className: "text-warning" };
  return { label: "Weak", className: "text-danger" };
}

const SEVERITY_ICON: Record<Evidence["severity"], React.ComponentType<{ className?: string }>> = {
  positive: CheckCircle2,
  info: Info,
  warning: TriangleAlert,
};

const SEVERITY_CLASS: Record<Evidence["severity"], string> = {
  positive: "text-success",
  info: "text-ink-subtle",
  warning: "text-warning",
};

function EvidenceRow({ evidence }: { evidence: Evidence }) {
  const Icon = SEVERITY_ICON[evidence.severity];
  return (
    <li className="flex items-start gap-2 text-sm text-ink-muted">
      <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", SEVERITY_CLASS[evidence.severity])} />
      <span>{evidence.message}</span>
    </li>
  );
}

function ComponentCard({
  component,
  defaultOpen,
}: {
  component: ComponentScore;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  const panelId = `component-${component.key}`;

  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center gap-4 p-4 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <span className="font-medium text-ink">{component.label}</span>
            <span className="tabular-nums text-sm font-semibold text-ink">
              {Math.round(component.score)}
            </span>
          </div>
          <ScoreBar score={component.score} className="mt-2" />
        </div>
        <ChevronDown
          aria-hidden
          className={cn("size-4 shrink-0 text-ink-subtle transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <CardContent id={panelId} className="pt-0">
          <p className="mb-3 text-sm text-ink-muted">{component.explanation}</p>
          <ul className="space-y-1.5">
            {component.evidence.map((item, index) => (
              <EvidenceRow key={index} evidence={item} />
            ))}
          </ul>
        </CardContent>
      ) : null}
    </Card>
  );
}

export function HealthReport({ result }: { result: ResumeHealthResult }) {
  const band = overallBand(result.overall);
  const orderedKeys = [
    ...COMPONENT_ORDER.filter((key) => key in result.components),
    ...Object.keys(result.components).filter((key) => !COMPONENT_ORDER.includes(key)),
  ];
  const lowestKey = orderedKeys.reduce((lowest, key) =>
    result.components[key]!.score < result.components[lowest]!.score ? key : lowest,
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Resume Health</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-6">
          <div className="text-5xl font-semibold tabular-nums text-ink">
            {Math.round(result.overall)}
          </div>
          <div>
            <p className={cn("font-medium", band.className)}>{band.label}</p>
            <p className="text-sm text-ink-subtle">
              Weighted across all six components below (methodology:{" "}
              {result.methodology.profile ?? "default"} v{result.methodology.version ?? "1.0.0"})
            </p>
          </div>
        </CardContent>
      </Card>

      {result.degraded.length > 0 ? (
        <p className="text-sm text-ink-subtle">
          Some components could not be computed and were excluded from the overall score:{" "}
          {result.degraded.join(", ")}.
        </p>
      ) : null}

      <div className="space-y-3">
        {orderedKeys.map((key) => (
          <ComponentCard
            key={key}
            component={result.components[key]!}
            defaultOpen={key === lowestKey}
          />
        ))}
      </div>
    </div>
  );
}
