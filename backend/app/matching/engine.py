"""Job-match scoring: orchestrates deterministic and semantic components (ARCHITECTURE.md
section 7).

Uses the same degrade-and-renormalise mechanism ``app.analysis.engine`` built in Phase 3 for a
future need - this is that need: ``project_relevance`` and ``semantic_relevance`` require the
embedding provider and report unavailable when it cannot be loaded, at which point their weight
is redistributed across the four deterministic components rather than silently treated as zero.
"""

from __future__ import annotations

from app.analysis.models import ComponentScore
from app.analysis.scoring_utils import apply_degrade_and_renormalize
from app.config import Settings
from app.jobs.models import JobDescription
from app.matching.config import DEFAULT_MATCH_PROFILE, MatchProfile
from app.matching.deterministic import (
    score_education,
    score_experience,
    score_preferred_skills,
    score_required_skills,
)
from app.matching.embeddings import get_embedding_provider
from app.matching.gaps import compute_skill_gaps
from app.matching.models import JobMatchResult
from app.matching.semantic import score_project_relevance, score_semantic_relevance
from app.resume.models import Resume


def compute_job_match(
    resume: Resume,
    job: JobDescription,
    settings: Settings,
    profile: MatchProfile = DEFAULT_MATCH_PROFILE,
) -> JobMatchResult:
    provider = get_embedding_provider(settings)

    components: dict[str, ComponentScore] = {
        "required_skills": score_required_skills(job, resume, profile.weights["required_skills"]),
        "preferred_skills": score_preferred_skills(
            job, resume, profile.weights["preferred_skills"]
        ),
        "experience": score_experience(job, resume, profile.weights["experience"]),
        "education": score_education(job, resume, profile.weights["education"]),
        "project_relevance": score_project_relevance(
            job, resume, provider, profile.weights["project_relevance"]
        ),
        "semantic_relevance": score_semantic_relevance(
            job, resume, provider, profile.weights["semantic_relevance"]
        ),
    }

    components, overall, degraded = apply_degrade_and_renormalize(components)
    skill_gaps = compute_skill_gaps(job, resume, provider)

    return JobMatchResult(
        overall=overall,
        components=components,
        degraded=degraded,
        methodology={"profile": profile.name, "version": profile.version},
        skill_gaps=skill_gaps,
    )
