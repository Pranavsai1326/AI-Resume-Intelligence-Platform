"""Unit tests for app.ai.tailor."""

from __future__ import annotations

from app.ai.providers import NullLLMProvider
from app.ai.tailor import (
    MAX_BULLET_REWRITES,
    TailorProposal,
    TailorProposalKind,
    TailorTarget,
    apply_proposals,
    generate_tailor_proposals,
)
from app.jobs.models import RequirementImportance
from app.matching.gaps import SkillGapBucket, SkillGapEntry, SkillGapResult
from tests.ai_fakes import FakeLLMProvider
from tests.fixtures import make_resume


def _gaps(entries: list[SkillGapEntry]) -> SkillGapResult:
    return SkillGapResult(entries=entries, semantic_available=False)


async def test_deterministic_reorder_skills_proposal_needs_no_ai() -> None:
    resume = make_resume()  # skills: [Python, Go, TypeScript], [Kubernetes, Terraform, AWS]
    gaps = _gaps(
        [
            SkillGapEntry(
                skill="TypeScript",
                requirement_text="TypeScript",
                importance=RequirementImportance.REQUIRED,
                bucket=SkillGapBucket.STRONG,
                evidence="listed",
            )
        ]
    )
    proposals = await generate_tailor_proposals(resume, gaps, NullLLMProvider())
    reorder = [p for p in proposals if p.kind == TailorProposalKind.REORDER_SKILLS]
    assert len(reorder) == 1
    assert reorder[0].requires_ai is False
    assert reorder[0].after == ["TypeScript", "Python", "Go"]


async def test_skill_reminder_proposal_for_missing_required_skill() -> None:
    resume = make_resume()
    gaps = _gaps(
        [
            SkillGapEntry(
                skill="Rust",
                requirement_text="Rust",
                importance=RequirementImportance.REQUIRED,
                bucket=SkillGapBucket.MISSING,
                evidence="not found",
            )
        ]
    )
    proposals = await generate_tailor_proposals(resume, gaps, NullLLMProvider())
    reminders = [p for p in proposals if p.kind == TailorProposalKind.SKILL_REMINDER]
    assert len(reminders) == 1
    assert reminders[0].requires_ai is False
    assert "Rust" in reminders[0].rationale


async def test_skill_reminder_not_generated_for_preferred_missing_skill() -> None:
    resume = make_resume()
    gaps = _gaps(
        [
            SkillGapEntry(
                skill="Rust",
                requirement_text="Rust",
                importance=RequirementImportance.PREFERRED,
                bucket=SkillGapBucket.MISSING,
                evidence="not found",
            )
        ]
    )
    proposals = await generate_tailor_proposals(resume, gaps, NullLLMProvider())
    assert not any(p.kind == TailorProposalKind.SKILL_REMINDER for p in proposals)


async def test_no_ai_proposals_without_available_provider() -> None:
    resume = make_resume()
    gaps = _gaps(
        [
            SkillGapEntry(
                skill="python",
                requirement_text="Python",
                importance=RequirementImportance.REQUIRED,
                bucket=SkillGapBucket.STRONG,
                evidence="mentioned in bullet",
            )
        ]
    )
    proposals = await generate_tailor_proposals(resume, gaps, NullLLMProvider())
    assert not any(p.kind == TailorProposalKind.BULLET_REWRITE for p in proposals)


async def test_ai_bullet_rewrites_are_capped_at_max_bullet_rewrites() -> None:
    from app.resume.models import ExperienceEntry
    from app.resume.provenance import Provenance, ProvenancedValue

    resume = make_resume()
    resume.experience = [
        ProvenancedValue(
            value=ExperienceEntry(
                title="Engineer",
                organization="Acme",
                bullets=[f"Worked with python on task {i}" for i in range(10)],
            ),
            provenance=Provenance.extracted(confidence=0.9),
        )
    ]
    gaps = _gaps(
        [
            SkillGapEntry(
                skill="python",
                requirement_text="Python",
                importance=RequirementImportance.REQUIRED,
                bucket=SkillGapBucket.STRONG,
                evidence="mentioned",
            )
        ]
    )
    fake = FakeLLMProvider(response_text="Rewritten bullet mentioning python.")
    proposals = await generate_tailor_proposals(resume, gaps, fake)
    rewrites = [p for p in proposals if p.kind == TailorProposalKind.BULLET_REWRITE]
    assert len(rewrites) == MAX_BULLET_REWRITES
    assert all(p.requires_ai for p in rewrites)


async def test_bullet_rewrite_proposal_carries_fact_guard_findings() -> None:
    resume = make_resume()
    gaps = _gaps(
        [
            SkillGapEntry(
                skill="kubernetes",
                requirement_text="Kubernetes",
                importance=RequirementImportance.REQUIRED,
                bucket=SkillGapBucket.STRONG,
                evidence="mentioned",
            )
        ]
    )
    # make_resume's bullets don't mention "kubernetes" so add one that does.
    resume.experience[0].value.bullets.append("Deployed services on kubernetes clusters")
    fake = FakeLLMProvider(response_text="Deployed services using Snowflake and Databricks.")
    proposals = await generate_tailor_proposals(resume, gaps, fake)
    rewrites = [p for p in proposals if p.kind == TailorProposalKind.BULLET_REWRITE]
    assert len(rewrites) == 1
    assert len(rewrites[0].fact_guard_findings) >= 1


def test_apply_proposals_does_not_mutate_input_resume() -> None:
    resume = make_resume()
    original_skills = list(resume.skills[0].value.skills)
    proposal = TailorProposal(
        proposal_id="p1",
        kind=TailorProposalKind.REORDER_SKILLS,
        rationale="reorder",
        target=TailorTarget(skill_group_index=0),
        before=original_skills,
        after=list(reversed(original_skills)),
        requires_ai=False,
    )
    updated = apply_proposals(resume, [proposal])
    assert resume.skills[0].value.skills == original_skills  # input untouched
    assert updated.skills[0].value.skills == list(reversed(original_skills))
    assert updated is not resume


def test_apply_proposals_bullet_rewrite() -> None:
    resume = make_resume()
    before_text = resume.experience[0].value.bullets[0]
    proposal = TailorProposal(
        proposal_id="p2",
        kind=TailorProposalKind.BULLET_REWRITE,
        rationale="rewrite",
        target=TailorTarget(experience_index=0, bullet_index=0),
        before=before_text,
        after="A much better bullet.",
        requires_ai=True,
    )
    updated = apply_proposals(resume, [proposal])
    assert updated.experience[0].value.bullets[0] == "A much better bullet."
    assert resume.experience[0].value.bullets[0] == before_text


def test_apply_proposals_ignores_out_of_range_targets() -> None:
    resume = make_resume()
    proposal = TailorProposal(
        proposal_id="p3",
        kind=TailorProposalKind.BULLET_REWRITE,
        rationale="rewrite",
        target=TailorTarget(experience_index=99, bullet_index=0),
        before="x",
        after="y",
        requires_ai=True,
    )
    updated = apply_proposals(resume, [proposal])
    # No crash, no change applied.
    assert updated.model_dump() == resume.model_dump()


def test_apply_proposals_skill_reminder_is_a_no_op() -> None:
    resume = make_resume()
    proposal = TailorProposal(
        proposal_id="p4",
        kind=TailorProposalKind.SKILL_REMINDER,
        rationale="consider adding Rust",
        target=TailorTarget(),
        requires_ai=False,
    )
    updated = apply_proposals(resume, [proposal])
    assert updated.model_dump() == resume.model_dump()
