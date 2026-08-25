"""AI-generated cover letter, grounded in the session's own resume and job facts.

A proposal, never a document the user is assumed to want unedited: the caller decides whether to
use it. Every paragraph is fact-guarded before being returned (AI_ARCHITECTURE.md section 5).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.ai.fact_guard import FactIndex, check
from app.ai.prompts import COVER_LETTER
from app.ai.providers import LLMProvider
from app.ai.structured import complete_structured
from app.jobs.models import JobDescription
from app.resume.models import Resume


class _CoverLetterSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    salutation: str
    body_paragraphs: list[str]
    closing: str


class CoverLetterProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    salutation: str | None = None
    body_paragraphs: list[str] = []
    closing: str | None = None
    fact_guard_findings: list[str] = []
    available: bool
    unavailable_reason: str | None = None


def _resume_context(resume: Resume, job: JobDescription) -> str:
    lines: list[str] = []
    if job.title:
        lines.append(f"Job title: {job.title}")
    required = [r.text for r in job.requirements if r.importance.value == "required"]
    if required:
        lines.append("Key requirements: " + "; ".join(required[:8]))
    if resume.summary:
        lines.append(f"Candidate summary: {resume.summary.value}")
    for entry in resume.experience[:3]:
        role = entry.value
        bullets = "; ".join(role.bullets[:3])
        lines.append(f"Experience: {role.title} at {role.organization}. {bullets}")
    if resume.skills:
        all_skills = [s for group in resume.skills for s in group.value.skills]
        lines.append("Skills: " + ", ".join(all_skills[:20]))
    return "\n".join(lines)


async def generate_cover_letter(
    resume: Resume, job: JobDescription, provider: LLMProvider
) -> CoverLetterProposal:
    if not provider.is_available():
        return CoverLetterProposal(
            available=False,
            unavailable_reason="AI writing is not configured on this deployment.",
        )

    parsed = await complete_structured(
        provider,
        spec=COVER_LETTER,
        user=_resume_context(resume, job),
        schema=_CoverLetterSchema,
    )
    if parsed is None:
        return CoverLetterProposal(
            available=False,
            unavailable_reason="The AI provider did not return a usable cover letter.",
        )

    index = FactIndex.build(resume, job)
    generated_text = " ".join(parsed.body_paragraphs)
    findings = check(generated_text, index)
    return CoverLetterProposal(
        salutation=parsed.salutation,
        body_paragraphs=parsed.body_paragraphs,
        closing=parsed.closing,
        fact_guard_findings=[f.message for f in findings],
        available=True,
    )
