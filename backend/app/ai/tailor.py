"""AI resume tailoring: turns Phase 4's job match into concrete, reviewable edit proposals.

Two layers (AI_ARCHITECTURE.md section 1):

* **Deterministic, always available** - reorder each skill group so job-relevant skills lead,
  and surface a reminder for required skills the resume shows no evidence of. A reminder, never
  a fabricated addition: the user decides whether they genuinely have that skill.
* **AI-assisted, needs a configured LLM** - re-emphasise the wording of bullets that already
  mention a job-relevant keyword, fact-guarded against the resume's own content. Bounded to a
  handful of bullets per AI_ARCHITECTURE.md section 7's token-discipline guidance: this is a
  proposal review, not a full-document rewrite.

Every proposal is a suggestion; nothing here mutates the resume. ``apply_proposals`` is a
separate, explicit step the caller invokes only for proposals the user accepted.
"""

from __future__ import annotations

import secrets

from pydantic import BaseModel, ConfigDict

from app.ai.fact_guard import FactIndex, check
from app.ai.prompts import TAILOR_BULLET
from app.ai.providers import LLMProvider
from app.analysis.taxonomy import contains_skill_mention
from app.jobs.models import RequirementImportance
from app.matching.gaps import SkillGapBucket, SkillGapResult
from app.resume.models import Resume

#: A proposal review, not a full-document rewrite - bounded per AI_ARCHITECTURE.md section 7.
MAX_BULLET_REWRITES = 3


class TailorProposalKind:
    REORDER_SKILLS = "reorder_skills"
    SKILL_REMINDER = "skill_reminder"
    BULLET_REWRITE = "bullet_rewrite"


class TailorTarget(BaseModel):
    """Where a proposal applies within the resume, so `apply_proposals` can locate it."""

    model_config = ConfigDict(extra="forbid")

    skill_group_index: int | None = None
    experience_index: int | None = None
    bullet_index: int | None = None


class TailorProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    kind: str
    rationale: str
    target: TailorTarget
    before: str | list[str] | None = None
    after: str | list[str] | None = None
    fact_guard_findings: list[str] = []
    requires_ai: bool


def _generate_deterministic_proposals(
    resume: Resume, gaps: SkillGapResult
) -> list[TailorProposal]:
    proposals: list[TailorProposal] = []
    relevant = {entry.skill.strip().lower() for entry in gaps.entries}

    for index, group in enumerate(resume.skills):
        current = group.value.skills
        relevant_first = [s for s in current if s.strip().lower() in relevant]
        rest = [s for s in current if s.strip().lower() not in relevant]
        reordered = relevant_first + rest
        if relevant_first and reordered != current:
            proposals.append(
                TailorProposal(
                    proposal_id=secrets.token_hex(6),
                    kind=TailorProposalKind.REORDER_SKILLS,
                    rationale=f"Move job-relevant skills ({', '.join(relevant_first)}) to the "
                    "front of this group so they're seen first.",
                    target=TailorTarget(skill_group_index=index),
                    before=current,
                    after=reordered,
                    requires_ai=False,
                )
            )

    for entry in gaps.entries:
        if entry.importance != RequirementImportance.REQUIRED:
            continue
        if entry.bucket not in (SkillGapBucket.MISSING, SkillGapBucket.INSUFFICIENT_EVIDENCE):
            continue
        proposals.append(
            TailorProposal(
                proposal_id=secrets.token_hex(6),
                kind=TailorProposalKind.SKILL_REMINDER,
                rationale=f'This role requires "{entry.skill}", which is not clearly shown in '
                "your resume. If you genuinely have relevant experience, consider adding it - "
                "nothing is added automatically.",
                target=TailorTarget(),
                requires_ai=False,
            )
        )

    return proposals


async def _generate_bullet_rewrite_proposals(
    resume: Resume, gaps: SkillGapResult, provider: LLMProvider
) -> list[TailorProposal]:
    if not provider.is_available():
        return []

    relevant = {
        entry.skill.strip().lower()
        for entry in gaps.entries
        if entry.bucket in (SkillGapBucket.STRONG, SkillGapBucket.MODERATE)
    }
    if not relevant:
        return []

    fact_index = FactIndex.build(resume)
    candidates: list[tuple[int, int, str, list[str]]] = []
    for experience_index, entry in enumerate(resume.experience):
        for bullet_index, bullet in enumerate(entry.value.bullets):
            matched = [k for k in relevant if contains_skill_mention(bullet, k)]
            if matched:
                candidates.append((experience_index, bullet_index, bullet, matched))
    candidates = candidates[:MAX_BULLET_REWRITES]

    proposals: list[TailorProposal] = []
    for experience_index, bullet_index, bullet, matched in candidates:
        user_message = (
            f"Bullet: {bullet}\nRelevant keywords already present: {', '.join(matched)}"
        )[: TAILOR_BULLET.max_input_chars]
        response = await provider.complete(
            system=TAILOR_BULLET.system,
            user=user_message,
            max_tokens=TAILOR_BULLET.max_output_tokens,
            temperature=TAILOR_BULLET.temperature,
        )
        if response is None or not response.text.strip():
            continue

        after = response.text.strip()
        findings = check(after, fact_index)
        proposals.append(
            TailorProposal(
                proposal_id=secrets.token_hex(6),
                kind=TailorProposalKind.BULLET_REWRITE,
                rationale=f"Re-emphasises {', '.join(matched)}, already present in this bullet, "
                "for this role.",
                target=TailorTarget(experience_index=experience_index, bullet_index=bullet_index),
                before=bullet,
                after=after,
                fact_guard_findings=[f.message for f in findings],
                requires_ai=True,
            )
        )
    return proposals


async def generate_tailor_proposals(
    resume: Resume, gaps: SkillGapResult, provider: LLMProvider
) -> list[TailorProposal]:
    proposals = _generate_deterministic_proposals(resume, gaps)
    proposals.extend(await _generate_bullet_rewrite_proposals(resume, gaps, provider))
    return proposals


def apply_proposals(resume: Resume, proposals: list[TailorProposal]) -> Resume:
    """Apply accepted proposals, producing a new Resume rather than mutating the input.

    Note on provenance: an accepted bullet rewrite replaces the bullet's text but the entry-level
    provenance stays EXTRACTED - the structured model tracks provenance per experience entry, not
    per bullet, so a finer-grained AI_GENERATED marking is not currently expressible. Documented
    as a known limitation rather than a silent gap.
    """
    updated = resume.model_copy(deep=True)
    for proposal in proposals:
        if (
            proposal.kind == TailorProposalKind.REORDER_SKILLS
            and proposal.target.skill_group_index is not None
            and isinstance(proposal.after, list)
        ):
            index = proposal.target.skill_group_index
            if 0 <= index < len(updated.skills):
                updated.skills[index].value.skills = list(proposal.after)
        elif (
            proposal.kind == TailorProposalKind.BULLET_REWRITE
            and proposal.target.experience_index is not None
            and proposal.target.bullet_index is not None
            and isinstance(proposal.after, str)
        ):
            ei, bi = proposal.target.experience_index, proposal.target.bullet_index
            valid = 0 <= ei < len(updated.experience) and 0 <= bi < len(
                updated.experience[ei].value.bullets
            )
            if valid:
                updated.experience[ei].value.bullets[bi] = proposal.after
    return updated
