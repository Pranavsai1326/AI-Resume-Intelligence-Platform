import { ComponentScoreList, overallBand } from "@/components/analysis/component-score-list";
import { SkillGapPanel } from "@/components/matching/skill-gap-panel";
import { cn } from "@/lib/utils";
import type { JobMatchResult } from "@/lib/api-client";

const COMPONENT_ORDER = [
  "required_skills",
  "preferred_skills",
  "experience",
  "education",
  "project_relevance",
  "semantic_relevance",
];

/* Phase 9E: no outer card, no methodology/version string - see HealthReport for the same change. */
export function JobMatchReport({ result }: { result: JobMatchResult }) {
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
          Semantic matching is not configured on this deployment, so{" "}
          {result.degraded.map((k) => k.replace(/_/g, " ")).join(" and ")} were excluded from the
          overall score and the remaining weights were redistributed.
        </p>
      ) : null}

      <ComponentScoreList components={result.components} order={COMPONENT_ORDER} />

      <SkillGapPanel result={result.skill_gaps} />
    </div>
  );
}
