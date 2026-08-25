"""Skills coverage: presence, breadth and grounding of the skills section.

Without a job description (Phase 4 adds that comparison), this component measures the skills
section on its own terms: does it exist, is it more than a token list, is it organised into
categories, and are the listed skills also demonstrated in the experience bullets rather than
only asserted in a list. The curated skills taxonomy (``app.analysis.taxonomy.COMMON_SKILLS``)
is used only to add positive credit for recognisable entries - an unrecognised skill is never
penalised, since the taxonomy is necessarily a small sample of real-world skills.
"""

from __future__ import annotations

from app.analysis.models import ComponentScore, Evidence, EvidenceSeverity
from app.analysis.scoring_utils import clamp_score
from app.analysis.taxonomy import COMMON_SKILLS
from app.analysis.text_metrics import bullets_of
from app.resume.models import Resume

MAX_SCORE = 100.0
MIN_SKILLS_FOR_FULL_CREDIT = 6


def score_skills_coverage(resume: Resume, weight: float) -> ComponentScore:
    evidence: list[Evidence] = []

    if not resume.skills:
        evidence.append(
            Evidence(message="No skills section was found.", severity=EvidenceSeverity.WARNING)
        )
        return ComponentScore(
            key="skills_coverage",
            label="Skills Coverage",
            score=0.0,
            weight=weight,
            evidence=evidence,
            explanation=(
                "Checks that a skills section exists, lists a meaningful number of skills, "
                "and that those skills are also referenced in the experience section. No "
                "skills section was found."
            ),
        )

    all_skills = [skill for group in resume.skills for skill in group.value.skills]
    score = 40.0  # base credit for having a skills section at all
    evidence.append(
        Evidence(
            message=f"{len(all_skills)} skill{'s' if len(all_skills) != 1 else ''} listed across "
            f"{len(resume.skills)} group{'s' if len(resume.skills) != 1 else ''}.",
            severity=EvidenceSeverity.POSITIVE,
        )
    )

    breadth_credit = min(30.0, (len(all_skills) / MIN_SKILLS_FOR_FULL_CREDIT) * 30.0)
    score += breadth_credit
    if len(all_skills) < MIN_SKILLS_FOR_FULL_CREDIT:
        evidence.append(
            Evidence(
                message=f"Fewer than {MIN_SKILLS_FOR_FULL_CREDIT} skills are listed; consider "
                "adding more if genuinely applicable.",
                severity=EvidenceSeverity.INFO,
            )
        )

    if any(group.value.category for group in resume.skills):
        score += 10
        evidence.append(
            Evidence(
                message="Skills are organised into categories.", severity=EvidenceSeverity.POSITIVE
            )
        )

    recognized = [s for s in all_skills if s.strip().lower() in COMMON_SKILLS]
    if all_skills:
        evidence.append(
            Evidence(
                message=f"{len(recognized)} of {len(all_skills)} listed skills matched common "
                "industry keywords.",
                severity=EvidenceSeverity.INFO,
            )
        )

    experience_text = " ".join(bullets_of(resume)).lower()
    if all_skills and experience_text:
        grounded = [s for s in all_skills if s.strip().lower() in experience_text]
        ratio = len(grounded) / len(all_skills)
        score += ratio * 20
        if ratio >= 0.3:
            evidence.append(
                Evidence(
                    message=f"{len(grounded)} of {len(all_skills)} listed skills are also "
                    "mentioned in the experience section, not just listed.",
                    severity=EvidenceSeverity.POSITIVE,
                )
            )
        else:
            evidence.append(
                Evidence(
                    message="Most listed skills are not mentioned anywhere in the experience "
                    "section - consider showing them in context.",
                    severity=EvidenceSeverity.INFO,
                )
            )

    return ComponentScore(
        key="skills_coverage",
        label="Skills Coverage",
        score=clamp_score(score),
        weight=weight,
        evidence=evidence,
        explanation=(
            "Checks that a skills section exists, lists a meaningful number of skills, is "
            "organised into categories, and that those skills are also referenced in the "
            "experience section rather than only asserted in a list."
        ),
    )
