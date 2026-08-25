"use client";

import { GitBranch } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { VersionSource, VersionSummary } from "@/lib/api-client";

/* Version list/switcher (PRD section 19): label, source, created-at, and lineage (based_on). */

const SOURCE_LABEL: Record<VersionSource, string> = {
  original: "Original",
  manual_edit: "Manual edit",
  ai_tailored: "AI tailored",
};

const SOURCE_VARIANT: Record<VersionSource, "neutral" | "accent" | "success"> = {
  original: "neutral",
  manual_edit: "accent",
  ai_tailored: "success",
};

export function VersionSwitcher({
  versions,
  currentVersionId,
  onSelect,
}: {
  versions: VersionSummary[];
  currentVersionId: string | null;
  onSelect: (versionId: string) => void;
}) {
  if (versions.length === 0) return null;

  const byId = new Map(versions.map((v) => [v.version_id, v]));

  return (
    <div className="space-y-2">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
        <GitBranch aria-hidden className="size-4 text-ink-subtle" />
        Versions
      </h3>
      <ul className="space-y-1.5">
        {versions.map((version) => {
          const basedOn = version.based_on_version_id
            ? byId.get(version.based_on_version_id)
            : null;
          const isCurrent = version.version_id === currentVersionId;
          return (
            <li key={version.version_id}>
              <button
                type="button"
                onClick={() => onSelect(version.version_id)}
                aria-current={isCurrent}
                className={cn(
                  "w-full rounded-card border px-3 py-2 text-left text-sm transition-colors",
                  isCurrent
                    ? "border-accent bg-accent-soft"
                    : "border-border bg-surface hover:bg-surface-muted",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-ink">{version.label}</span>
                  <Badge variant={SOURCE_VARIANT[version.source]}>
                    {SOURCE_LABEL[version.source]}
                  </Badge>
                </div>
                <p className="mt-0.5 text-xs text-ink-subtle">
                  {new Date(version.created_at).toLocaleString()}
                  {basedOn ? ` · based on “${basedOn.label}”` : ""}
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
