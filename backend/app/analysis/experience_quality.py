"""Experience quality: how thoroughly and clearly each role is documented.

Distinct from Content Quality (phrasing) and Impact (outcome framing): this component asks
whether each experience entry has enough detail to evaluate at all - bullets per role, dates,
and organisation/title present - independent of how well-written the bullets are.
"""

from __future__ import annotations

from app.analysis.models import ComponentScore, Evidence, EvidenceSeverity
from app.analysis.scoring_utils import clamp_score
from app.analysis.text_metrics import has_quantification, starts_with_action_verb
from app.resume.models import Resume

MAX_SCORE = 100.0
TARGET_BULLETS_PER_ROLE = 3.0


def score_experience_quality(resume: Resume, weight: float) -> ComponentScore:
    evidence: list[Evidence] = []

    if not resume.experience:
        evidence.append(
            Evidence(
                message="No work experience entries were found.", severity=EvidenceSeverity.WARNING
            )
        )
        return ComponentScore(
            key="experience_quality",
            label="Experience Quality",
            score=0.0,
            weight=weight,
            evidence=evidence,
            explanation=(
                "Checks that each role has enough detail to evaluate: bullet points, dates, "
                "quantified outcomes and action-verb-led descriptions. No experience entries "
                "were found."
            ),
        )

    entries = [e.value for e in resume.experience]
    score = 20.0  # base credit for having at least one entry

    all_bullets = [b for e in entries for b in e.bullets]
    avg_bullets = len(all_bullets) / len(entries)
    bullet_credit = min(25.0, (avg_bullets / TARGET_BULLETS_PER_ROLE) * 25.0)
    score += bullet_credit
    evidence.append(
        Evidence(
            message=f"An average of {avg_bullets:.1f} bullet points per role.",
            severity=EvidenceSeverity.POSITIVE if avg_bullets >= 2 else EvidenceSeverity.WARNING,
        )
    )

    with_dates = sum(1 for e in entries if e.dates is not None)
    date_ratio = with_dates / len(entries)
    score += date_ratio * 20
    if date_ratio < 1.0:
        evidence.append(
            Evidence(
                message=f"Dates are missing or unrecognised for {len(entries) - with_dates} of "
                f"{len(entries)} roles.",
                severity=EvidenceSeverity.WARNING,
            )
        )
    else:
        evidence.append(
            Evidence(
                message="Every role has recognisable dates.", severity=EvidenceSeverity.POSITIVE
            )
        )

    with_org = sum(1 for e in entries if e.organization.strip())
    score += (with_org / len(entries)) * 10

    if all_bullets:
        quantified = sum(1 for b in all_bullets if has_quantification(b))
        quant_ratio = quantified / len(all_bullets)
        score += min(15.0, quant_ratio * 30)
        if quant_ratio >= 0.3:
            evidence.append(
                Evidence(
                    message=f"{quantified} of {len(all_bullets)} bullets include a number "
                    "suggesting a measurable outcome.",
                    severity=EvidenceSeverity.POSITIVE,
                )
            )
        else:
            evidence.append(
                Evidence(
                    message="Few bullets include a number - consider quantifying outcomes "
                    "where possible (team size, percentage improvement, scale).",
                    severity=EvidenceSeverity.INFO,
                )
            )

        action_ratio = sum(1 for b in all_bullets if starts_with_action_verb(b)) / len(all_bullets)
        score += action_ratio * 10

    return ComponentScore(
        key="experience_quality",
        label="Experience Quality",
        score=clamp_score(score),
        weight=weight,
        evidence=evidence,
        explanation=(
            "Checks that each role has enough detail to evaluate: bullet points per role, "
            "recognisable dates, and how often outcomes are quantified or led with an action "
            "verb."
        ),
    )
