"""Learning priorities: turn Phase 4's skill-gap buckets into a ranked "what to learn next" list.

Entirely deterministic (Layer 1 of AI_ARCHITECTURE.md) - this reorders and explains data the
scoring engine already computed, adding no new signal and needing no LLM. A required skill the
resume shows no evidence of outranks a preferred one; within the same importance, a flat MISSING
outranks INSUFFICIENT_EVIDENCE (something plausibly related is already listed, so the gap is
smaller) which outranks MODERATE (partial evidence already exists). STRONG skills are not gaps at
all and are excluded.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.models import RequirementImportance
from app.matching.gaps import SkillGapBucket, SkillGapEntry, SkillGapResult

#: Lower sorts first. STRONG is intentionally absent - it is never a gap.
_BUCKET_RANK = {
    SkillGapBucket.MISSING: 0,
    SkillGapBucket.INSUFFICIENT_EVIDENCE: 1,
    SkillGapBucket.MODERATE: 2,
}
_IMPORTANCE_RANK = {
    RequirementImportance.REQUIRED: 0,
    RequirementImportance.PREFERRED: 1,
    RequirementImportance.OPTIONAL: 2,
}

_REASON_BY_BUCKET = {
    SkillGapBucket.MISSING: "Not found anywhere in your resume - the most direct gap to close.",
    SkillGapBucket.INSUFFICIENT_EVIDENCE: (
        "A related skill is listed, but nothing directly confirms this one - worth strengthening "
        "or clarifying."
    ),
    SkillGapBucket.MODERATE: (
        "Partially shown (listed or mentioned, but not both) - worth reinforcing with concrete "
        "evidence."
    ),
}


class LearningPriority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    requirement_text: str
    importance: RequirementImportance
    bucket: SkillGapBucket
    reason: str


class LearningPriorityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priorities: list[LearningPriority] = Field(default_factory=list)
    semantic_available: bool


def _sort_key(entry: SkillGapEntry) -> tuple[int, int, str]:
    return (_IMPORTANCE_RANK[entry.importance], _BUCKET_RANK[entry.bucket], entry.skill)


def compute_learning_priorities(gaps: SkillGapResult) -> LearningPriorityResult:
    gap_entries = [e for e in gaps.entries if e.bucket != SkillGapBucket.STRONG]
    ordered = sorted(gap_entries, key=_sort_key)
    priorities = [
        LearningPriority(
            skill=entry.skill,
            requirement_text=entry.requirement_text,
            importance=entry.importance,
            bucket=entry.bucket,
            reason=_REASON_BY_BUCKET[entry.bucket],
        )
        for entry in ordered
    ]
    return LearningPriorityResult(priorities=priorities, semantic_available=gaps.semantic_available)
