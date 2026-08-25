"""Impact: how strongly the resume frames outcomes rather than activities.

Overlaps in raw material with Experience Quality (both look at quantification) but asks a
different question: not "is this role documented" but "does the resume as a whole read as a
record of results" - the density of quantified claims and outcome-oriented verbs ("reduced",
"grew", "delivered") across every bullet, not just experience bullets.
"""

from __future__ import annotations

from app.analysis.models import ComponentScore, Evidence, EvidenceSeverity
from app.analysis.scoring_utils import clamp_score
from app.analysis.text_metrics import bullets_of, has_quantification, starts_with_outcome_verb
from app.resume.models import Resume

MAX_SCORE = 100.0
MIN_BULLETS_FOR_FULL_CREDIT = 6


def score_impact(resume: Resume, weight: float) -> ComponentScore:
    evidence: list[Evidence] = []
    bullets = bullets_of(resume)

    if not bullets:
        evidence.append(
            Evidence(
                message="No bullet points were found to evaluate for impact.",
                severity=EvidenceSeverity.WARNING,
            )
        )
        return ComponentScore(
            key="impact",
            label="Impact",
            score=0.0,
            weight=weight,
            evidence=evidence,
            explanation=(
                "Measures how much of the resume reads as quantified results rather than "
                "activities: the share of bullets with a number, the share led by an "
                "outcome-oriented verb, and whether there is enough content to judge from. No "
                "bullets were available to evaluate."
            ),
        )

    quantified = sum(1 for b in bullets if has_quantification(b))
    quant_ratio = quantified / len(bullets)
    outcome_verb_hits = sum(1 for b in bullets if starts_with_outcome_verb(b))
    outcome_ratio = outcome_verb_hits / len(bullets)

    volume_credit = min(20.0, (len(bullets) / MIN_BULLETS_FOR_FULL_CREDIT) * 20.0)
    quant_credit = quant_ratio * 50.0
    outcome_credit = outcome_ratio * 30.0
    score = volume_credit + quant_credit + outcome_credit

    evidence.append(
        Evidence(
            message=f"{quantified} of {len(bullets)} bullets ({quant_ratio:.0%}) include a "
            "quantified detail.",
            severity=EvidenceSeverity.POSITIVE if quant_ratio >= 0.4 else EvidenceSeverity.WARNING,
        )
    )
    evidence.append(
        Evidence(
            message=f"{outcome_verb_hits} of {len(bullets)} bullets ({outcome_ratio:.0%}) open "
            'with an outcome-oriented verb (e.g. "reduced", "grew", "delivered").',
            severity=EvidenceSeverity.POSITIVE if outcome_ratio >= 0.3 else EvidenceSeverity.INFO,
        )
    )
    if len(bullets) < MIN_BULLETS_FOR_FULL_CREDIT:
        evidence.append(
            Evidence(
                message=f"Only {len(bullets)} bullet point"
                f"{'s' if len(bullets) != 1 else ''} in total - there may not be enough "
                "content here to demonstrate impact.",
                severity=EvidenceSeverity.INFO,
            )
        )

    return ComponentScore(
        key="impact",
        label="Impact",
        score=clamp_score(score),
        weight=weight,
        evidence=evidence,
        explanation=(
            "Measures how much of the resume reads as quantified results rather than "
            "activities: the share of bullets with a number, the share led by an "
            "outcome-oriented verb, and whether there is enough content to judge from."
        ),
    )
