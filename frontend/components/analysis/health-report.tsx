import { ComponentScoreList, overallBand } from "@/components/analysis/component-score-list";
import { cn } from "@/lib/utils";
import type { ResumeHealthResult } from "@/lib/api-client";

const COMPONENT_ORDER = [
  "ats_compatibility",
  "content_quality",
  "experience_quality",
  "skills_coverage",
  "formatting",
  "impact",
];

/*
  Phase 9E: no outer card, no methodology/version string - the overall score and band sit
  directly under the section heading the caller provides, followed by the component breakdown.
*/
export function HealthReport({ result }: { result: ResumeHealthResult }) {
  const band = overallBand(result.overall);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-6">
        <div className="text-[length:var(--text-display)] font-semibold tabular-nums text-ink">
          {Math.round(result.overall)}
        </div>
        <p className={cn("font-medium", band.className)}>{band.label}</p>
      </div>

      {result.degraded.length > 0 ? (
        <p className="text-sm text-ink-subtle">
          Some components could not be computed and were excluded from the overall score:{" "}
          {result.degraded.join(", ")}.
        </p>
      ) : null}

      <ComponentScoreList components={result.components} order={COMPONENT_ORDER} />
    </div>
  );
}
