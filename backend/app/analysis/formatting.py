"""Formatting: structural completeness and presentation, distinct from raw ATS parseability.

Where ATS Compatibility (``app.analysis.ats``) asks "can a machine read this at all", Formatting
asks "is it organised the way a resume conventionally is": the standard sections present, each
experience entry backed by bullets rather than a wall of prose, and - where page count is even
meaningful (PDF only; DOCX and TXT have no fixed pagination without rendering) - a length in the
range a reviewer expects.
"""

from __future__ import annotations

from app.analysis.models import ComponentScore, Evidence, EvidenceSeverity
from app.analysis.scoring_utils import clamp_score
from app.documents.extract.base import LayoutSignals
from app.resume.models import Resume

MAX_SCORE = 100.0

_SECTION_CHECKS: tuple[tuple[str, float, str, str], ...] = (
    ("summary", 10, "summary", "A"),
    ("experience", 25, "experience", "An"),
    ("education", 15, "education", "An"),
    ("skills", 15, "skills", "A"),
)


def score_formatting(resume: Resume, layout: LayoutSignals, weight: float) -> ComponentScore:
    score = MAX_SCORE
    evidence: list[Evidence] = []

    for attribute, penalty, label, article in _SECTION_CHECKS:
        present = bool(getattr(resume, attribute))
        if present:
            evidence.append(
                Evidence(
                    message=f"{article} {label} section was found.",
                    severity=EvidenceSeverity.POSITIVE,
                )
            )
        else:
            score -= penalty
            evidence.append(
                Evidence(
                    message=f"No {label} section was found.", severity=EvidenceSeverity.WARNING
                )
            )

    if resume.experience:
        with_bullets = sum(1 for e in resume.experience if e.value.bullets)
        if with_bullets < len(resume.experience):
            missing = len(resume.experience) - with_bullets
            score -= min(20, missing * 7)
            evidence.append(
                Evidence(
                    message=f"{missing} experience entr{'y' if missing == 1 else 'ies'} have no "
                    "bullet points describing the role.",
                    severity=EvidenceSeverity.WARNING,
                )
            )
        else:
            evidence.append(
                Evidence(
                    message="Every experience entry includes bullet points.",
                    severity=EvidenceSeverity.POSITIVE,
                )
            )

    if layout.page_count is not None:
        if layout.page_count <= 2:
            evidence.append(
                Evidence(
                    message=f"The document is {layout.page_count} page"
                    f"{'s' if layout.page_count != 1 else ''} long, within the conventional range.",
                    severity=EvidenceSeverity.POSITIVE,
                )
            )
        elif layout.page_count == 3:
            score -= 5
            evidence.append(
                Evidence(
                    message="The document is 3 pages long, longer than the 1-2 pages most "
                    "resumes are reviewed at.",
                    severity=EvidenceSeverity.INFO,
                )
            )
        else:
            score -= 15
            evidence.append(
                Evidence(
                    message=f"The document is {layout.page_count} pages long, well beyond the "
                    "1-2 pages most resumes are reviewed at.",
                    severity=EvidenceSeverity.WARNING,
                )
            )

    return ComponentScore(
        key="formatting",
        label="Formatting",
        score=clamp_score(score),
        weight=weight,
        evidence=evidence,
        explanation=(
            "Checks that the conventional resume sections are present, that experience entries "
            "are backed by bullet points rather than prose, and - where page count is "
            "measurable - that the document length is in the range a reviewer typically expects."
        ),
    )
