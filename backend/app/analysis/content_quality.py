"""Content quality: how the bullets are written, independent of what they claim.

Checks phrasing patterns known to weaken a resume bullet - passive, vague framing ("responsible
for"), first-person pronouns (resumes are conventionally written without "I"), and bullets that
are too short to say anything or long enough to bury the point. None of this touches whether the
claims are *true* or *impressive* - that is Impact and Experience Quality's job.
"""

from __future__ import annotations

from app.analysis.models import ComponentScore, Evidence, EvidenceSeverity
from app.analysis.scoring_utils import clamp_score
from app.analysis.text_metrics import (
    bullets_of,
    starts_with_action_verb,
    uses_first_person,
    weak_phrases_in,
    word_count,
)
from app.resume.models import Resume

MAX_SCORE = 100.0
MIN_REASONABLE_WORDS = 4
MAX_REASONABLE_WORDS = 40


def score_content_quality(resume: Resume, weight: float) -> ComponentScore:
    score = MAX_SCORE
    evidence: list[Evidence] = []
    bullets = bullets_of(resume)

    if not bullets:
        evidence.append(
            Evidence(
                message="No bullet points were found to evaluate.",
                severity=EvidenceSeverity.WARNING,
            )
        )
        return ComponentScore(
            key="content_quality",
            label="Content Quality",
            score=0.0,
            weight=weight,
            evidence=evidence,
            explanation=(
                "Evaluates phrasing across experience and project bullets: action-verb usage, "
                "weak or passive phrasing, first-person pronouns, and bullet length. No bullets "
                "were available to evaluate."
            ),
        )

    weak_hits = sum(1 for b in bullets if weak_phrases_in(b))
    if weak_hits:
        ratio = weak_hits / len(bullets)
        score -= min(25, ratio * 60)
        evidence.append(
            Evidence(
                message=f"{weak_hits} of {len(bullets)} bullets use vague phrasing such as "
                '"responsible for" or "helped with" instead of a direct action verb.',
                severity=EvidenceSeverity.WARNING,
            )
        )
    else:
        evidence.append(
            Evidence(
                message="No vague or passive phrasing patterns were found.",
                severity=EvidenceSeverity.POSITIVE,
            )
        )

    first_person_hits = sum(1 for b in bullets if uses_first_person(b))
    if first_person_hits:
        score -= min(15, first_person_hits * 5)
        noun = "bullet" if first_person_hits == 1 else "bullets"
        verb = "uses" if first_person_hits == 1 else "use"
        evidence.append(
            Evidence(
                message=f"{first_person_hits} {noun} {verb} first-person pronouns "
                '("I", "my"), which resumes conventionally omit.',
                severity=EvidenceSeverity.WARNING,
            )
        )

    action_verb_hits = sum(1 for b in bullets if starts_with_action_verb(b))
    action_ratio = action_verb_hits / len(bullets)
    if action_ratio >= 0.6:
        evidence.append(
            Evidence(
                message=f"{action_verb_hits} of {len(bullets)} bullets open with a direct "
                "action verb.",
                severity=EvidenceSeverity.POSITIVE,
            )
        )
    else:
        score -= (0.6 - action_ratio) * 40
        evidence.append(
            Evidence(
                message=f"Only {action_verb_hits} of {len(bullets)} bullets open with a "
                "recognisable action verb.",
                severity=EvidenceSeverity.WARNING,
            )
        )

    length_issues = sum(
        1
        for b in bullets
        if word_count(b) < MIN_REASONABLE_WORDS or word_count(b) > MAX_REASONABLE_WORDS
    )
    if length_issues:
        score -= min(15, length_issues * 4)
        evidence.append(
            Evidence(
                message=f"{length_issues} bullet{'s' if length_issues != 1 else ''} "
                f"{'are' if length_issues != 1 else 'is'} unusually short or long for a resume "
                "bullet point.",
                severity=EvidenceSeverity.INFO,
            )
        )

    return ComponentScore(
        key="content_quality",
        label="Content Quality",
        score=clamp_score(score),
        weight=weight,
        evidence=evidence,
        explanation=(
            "Evaluates phrasing across experience and project bullets: action-verb usage, weak "
            "or passive phrasing, first-person pronouns, and bullet length."
        ),
    )
