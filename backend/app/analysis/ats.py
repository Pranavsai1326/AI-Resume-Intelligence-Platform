"""ATS compatibility: how reliably an automated parser can read this document.

Two families of checks (PRD section 14):

* **Parsing simulation** - can the deterministic pipeline itself find a name, email, phone,
  work-history section and dates? If our own extractor (which is more forgiving than most
  commercial ATS parsers) struggles, a stricter parser is likely to struggle more.
* **Formatting risk** - layout features known to break or confuse ATS parsers: multi-column
  layout (text reads out of order), tables (cell content is often dropped or reordered), images
  (a photo carries no parseable text and may itself be a rejection trigger for some ATS), text
  boxes (frequently skipped entirely by parsers that only read the main text flow), and a
  repeating header/footer (contact details placed there can be stripped along with page furniture).

Point values are deterministic and documented at the point of use - not tuned against any real
ATS product, and the product never claims equivalence to one (PRD section 13).
"""

from __future__ import annotations

from app.analysis.models import ComponentScore, Evidence, EvidenceSeverity
from app.analysis.scoring_utils import clamp_score
from app.documents.extract.base import LayoutSignals
from app.resume.models import Resume

MAX_SCORE = 100.0

_PARSING_CHECKS: tuple[tuple[str, float, str, str], ...] = (
    # (resume attribute path handled below, penalty, warning message, positive message)
    ("name", 15, "No name was detected near the top of the document.", "A name was detected."),
    ("email", 15, "No email address was detected.", "An email address was detected."),
    ("phone", 5, "No phone number was detected.", "A phone number was detected."),
)

FORMATTING_RISKS: tuple[tuple[str, float, str], ...] = (
    (
        "multi_column",
        15,
        "The layout appears to use multiple columns, which many ATS parsers read out of "
        "reading order, scrambling the extracted text.",
    ),
    (
        "has_tables",
        10,
        "The document contains a table. Table cell content is frequently dropped or "
        "reordered by ATS parsers.",
    ),
    (
        "has_images",
        5,
        "The document contains an image. Image content (including a photo) is invisible to "
        "text-based ATS parsers.",
    ),
    (
        "has_text_boxes",
        10,
        "The document uses floating text boxes, which many ATS parsers skip entirely.",
    ),
    (
        "has_repeating_header_footer",
        5,
        "Repeating header/footer text was detected. Contact details placed there can be "
        "stripped along with page furniture by some parsers.",
    ),
)


def score_ats_compatibility(resume: Resume, layout: LayoutSignals, weight: float) -> ComponentScore:
    score = MAX_SCORE
    evidence: list[Evidence] = []

    contact_present = {
        "name": resume.contact.full_name is not None,
        "email": resume.contact.email is not None,
        "phone": resume.contact.phone is not None,
    }
    for field, penalty, warning, positive in _PARSING_CHECKS:
        if contact_present[field]:
            evidence.append(Evidence(message=positive, severity=EvidenceSeverity.POSITIVE))
        else:
            score -= penalty
            evidence.append(Evidence(message=warning, severity=EvidenceSeverity.WARNING))

    if resume.experience:
        count = len(resume.experience)
        noun = "entry" if count == 1 else "entries"
        verb = "was" if count == 1 else "were"
        evidence.append(
            Evidence(
                message=f"{count} work experience {noun} {verb} detected.",
                severity=EvidenceSeverity.POSITIVE,
            )
        )
    else:
        score -= 20
        evidence.append(
            Evidence(
                message="No work experience section was detected.",
                severity=EvidenceSeverity.WARNING,
            )
        )

    if resume.experience:
        with_dates = sum(1 for entry in resume.experience if entry.value.dates is not None)
        ratio = with_dates / len(resume.experience)
        if ratio < 0.5:
            score -= 10
            evidence.append(
                Evidence(
                    message=(
                        f"Dates could not be identified for {len(resume.experience) - with_dates} "
                        f"of {len(resume.experience)} experience entries."
                    ),
                    severity=EvidenceSeverity.WARNING,
                )
            )

    for attribute, penalty, message in FORMATTING_RISKS:
        if getattr(layout, attribute):
            score -= penalty
            evidence.append(Evidence(message=message, severity=EvidenceSeverity.WARNING))

    if not any(getattr(layout, attribute) for attribute, _, _ in FORMATTING_RISKS):
        evidence.append(
            Evidence(
                message="No common ATS formatting risks (columns, tables, images, text boxes) "
                "were detected.",
                severity=EvidenceSeverity.POSITIVE,
            )
        )

    return ComponentScore(
        key="ats_compatibility",
        label="ATS Compatibility",
        score=clamp_score(score),
        weight=weight,
        evidence=evidence,
        explanation=(
            "Simulates how an automated resume parser would read this document: whether contact "
            "details, work history and dates are detectable, and whether the layout (columns, "
            "tables, images, text boxes, repeating headers) is likely to confuse a parser."
        ),
    )
