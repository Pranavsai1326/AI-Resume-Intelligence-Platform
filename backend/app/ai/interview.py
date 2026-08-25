"""AI-generated interview preparation set, grounded in the session's own resume and job facts.

Each question carries a rationale traced to a specific resume or job detail, not a generic
question-bank item (AI_ARCHITECTURE.md section 9). Fact-guarded the same way rewriting and cover
letters are: a rationale that cites something absent from the resume or job is flagged, never
silently trusted.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ai.fact_guard import FactIndex, check
from app.ai.prompts import INTERVIEW_QUESTIONS
from app.ai.providers import LLMProvider
from app.ai.structured import complete_structured
from app.jobs.models import JobDescription
from app.resume.models import Resume

QuestionCategory = Literal["behavioral", "technical", "situational", "role_fit"]


class _InterviewQuestionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    category: QuestionCategory
    rationale: str
    grounded_in: str


class _InterviewQuestionsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[_InterviewQuestionSchema]


class InterviewQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    category: QuestionCategory
    rationale: str
    grounded_in: str
    fact_guard_findings: list[str] = []


class InterviewPrepProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[InterviewQuestion] = []
    available: bool
    unavailable_reason: str | None = None
    #: Total tokens spent generating this proposal (0 when unavailable) - a count, never content,
    #: for session-level cost tracking (SECURITY.md section 4).
    tokens_used: int = 0


def _resume_context(resume: Resume, job: JobDescription) -> str:
    lines: list[str] = []
    if job.title:
        lines.append(f"Job title: {job.title}")
    requirement_texts = [r.text for r in job.requirements]
    if requirement_texts:
        lines.append("Requirements: " + "; ".join(requirement_texts[:10]))
    if resume.summary:
        lines.append(f"Candidate summary: {resume.summary.value}")
    for entry in resume.experience[:4]:
        role = entry.value
        bullets = "; ".join(role.bullets[:4])
        lines.append(f"Experience: {role.title} at {role.organization}. {bullets}")
    if resume.projects:
        for project in resume.projects[:2]:
            lines.append(f"Project: {project.value.name}. {project.value.description or ''}")
    if resume.skills:
        all_skills = [s for group in resume.skills for s in group.value.skills]
        lines.append("Skills: " + ", ".join(all_skills[:20]))
    return "\n".join(lines)


async def generate_interview_questions(
    resume: Resume, job: JobDescription, provider: LLMProvider
) -> InterviewPrepProposal:
    if not provider.is_available():
        return InterviewPrepProposal(
            available=False,
            unavailable_reason="AI writing is not configured on this deployment.",
        )

    parsed, tokens_used = await complete_structured(
        provider,
        spec=INTERVIEW_QUESTIONS,
        user=_resume_context(resume, job),
        schema=_InterviewQuestionsSchema,
    )
    if parsed is None:
        return InterviewPrepProposal(
            available=False,
            unavailable_reason="The AI provider did not return a usable question set.",
            tokens_used=tokens_used,
        )

    index = FactIndex.build(resume, job)
    questions = [
        InterviewQuestion(
            question=q.question,
            category=q.category,
            rationale=q.rationale,
            grounded_in=q.grounded_in,
            fact_guard_findings=[f.message for f in check(f"{q.rationale} {q.grounded_in}", index)],
        )
        for q in parsed.questions
    ]
    return InterviewPrepProposal(questions=questions, available=True, tokens_used=tokens_used)
