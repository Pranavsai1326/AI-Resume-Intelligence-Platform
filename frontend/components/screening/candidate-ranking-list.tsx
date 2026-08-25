"use client";

import * as React from "react";
import { Star } from "lucide-react";

import { ScoreBar } from "@/components/analysis/score-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { CandidateResult } from "@/lib/api-client";

/*
  Ranked list - order is always Layer 1 (AI_ARCHITECTURE.md section 9), sorted purely by the
  score already computed server-side. Selecting candidates here feeds the comparison matrix;
  opening one feeds CandidateDetail's "why ranked #N" breakdown.
*/

export function CandidateRankingList({
  candidates,
  selected,
  onToggleSelect,
  onOpen,
}: {
  candidates: CandidateResult[];
  selected: Set<string>;
  onToggleSelect: (candidateId: string) => void;
  onOpen: (candidateId: string) => void;
}) {
  if (candidates.length === 0) {
    return <p className="text-sm text-ink-muted">No completed candidates yet.</p>;
  }

  return (
    <ul className="space-y-2">
      {candidates.map((candidate, index) => (
        <li key={candidate.candidate_id}>
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <input
                type="checkbox"
                checked={selected.has(candidate.candidate_id)}
                onChange={() => onToggleSelect(candidate.candidate_id)}
                aria-label={`Select candidate ${index + 1} for comparison`}
              />
              <span className="w-6 text-sm font-medium text-ink-subtle">#{index + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-ink">
                    Candidate {candidate.candidate_id.slice(0, 8)}
                  </span>
                  {candidate.shortlisted ? (
                    <Badge variant="success">
                      <Star aria-hidden className="size-3" />
                      Shortlisted
                    </Badge>
                  ) : null}
                </div>
                <ScoreBar score={candidate.match.overall} className="mt-2" />
              </div>
              <span className="w-10 text-right tabular-nums text-sm font-semibold text-ink">
                {Math.round(candidate.match.overall)}
              </span>
              <Button variant="ghost" size="sm" onClick={() => onOpen(candidate.candidate_id)}>
                View
              </Button>
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
