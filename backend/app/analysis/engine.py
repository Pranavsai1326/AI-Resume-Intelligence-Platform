"""Resume health: orchestrates the six components into one explainable result.

Every component here is fully deterministic (Layer 1) and needs no external dependency, so
nothing is ever unavailable in this phase - but the degrade-and-renormalise mechanism is built
now so a future component that does need one (e.g. a semantic-relevance score needing
embeddings) degrades the exact same way rather than as a special case bolted on later.
"""

from __future__ import annotations

from app.analysis.ats import score_ats_compatibility
from app.analysis.config import DEFAULT_PROFILE, ScoringProfile
from app.analysis.content_quality import score_content_quality
from app.analysis.experience_quality import score_experience_quality
from app.analysis.formatting import score_formatting
from app.analysis.impact import score_impact
from app.analysis.models import ComponentScore, ResumeHealthResult
from app.analysis.scoring_utils import apply_degrade_and_renormalize
from app.analysis.skills_coverage import score_skills_coverage
from app.documents.extract.base import LayoutSignals
from app.resume.models import Resume


def compute_resume_health(
    resume: Resume, layout: LayoutSignals, profile: ScoringProfile = DEFAULT_PROFILE
) -> ResumeHealthResult:
    components: dict[str, ComponentScore] = {
        "ats_compatibility": score_ats_compatibility(
            resume, layout, profile.weights["ats_compatibility"]
        ),
        "formatting": score_formatting(resume, layout, profile.weights["formatting"]),
        "content_quality": score_content_quality(resume, profile.weights["content_quality"]),
        "skills_coverage": score_skills_coverage(resume, profile.weights["skills_coverage"]),
        "experience_quality": score_experience_quality(
            resume, profile.weights["experience_quality"]
        ),
        "impact": score_impact(resume, profile.weights["impact"]),
    }

    components, overall, degraded = apply_degrade_and_renormalize(components)

    return ResumeHealthResult(
        overall=overall,
        components=components,
        degraded=degraded,
        methodology={"profile": profile.name, "version": profile.version},
    )
