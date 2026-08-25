"""Anti-hallucination fact guard (AI_ARCHITECTURE.md section 5).

Generated text is checked against a fact index built from the user's own session content before
it is ever shown: a number, an organisation, or a technology that does not appear anywhere in
the source is flagged as an unsupported claim. This is code, not a prompt instruction - prompts
in ``app.ai.prompts`` also tell the model not to invent facts, but that is not a control by
itself; this is.

The guard is deliberately conservative in one direction only: it may occasionally flag a
paraphrase it doesn't recognise as a false positive (a number reformatted, "40%" -> "forty
percent"), but it must never let through a number, name, or technology genuinely absent from the
source. A false positive costs the user a moment's review; a false negative is a fabricated fact
reaching them unlabelled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.resume.models import Resume

_NUMBER_RE = re.compile(r"\b\d[\d,.]*%?\b")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{2,}")

#: Common words excluded from the "technology/org" comparison - otherwise nearly every generated
#: sentence would trip on ordinary vocabulary that happens not to appear verbatim in the source.
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "into", "onto", "was", "were",
        "have", "has", "had", "using", "used", "team", "role", "work", "worked", "led",
        "built", "created", "developed", "improved", "managed", "designed", "implemented",
        "delivered", "supported", "including", "across", "within", "through", "while", "also",
    }
)


@dataclass(slots=True)
class FactGuardFinding:
    message: str
    #: The specific token (a number or a capitalised/technical word) that triggered the finding.
    token: str


@dataclass(slots=True)
class FactIndex:
    numbers: set[str] = field(default_factory=set)
    words: set[str] = field(default_factory=set)

    @staticmethod
    def build(resume: Resume) -> FactIndex:
        pieces: list[str] = []
        if resume.summary:
            pieces.append(resume.summary.value)
        for experience in resume.experience:
            pieces.append(experience.value.title)
            pieces.append(experience.value.organization)
            pieces.extend(experience.value.bullets)
        for education in resume.education:
            pieces.append(education.value.institution)
            if education.value.degree:
                pieces.append(education.value.degree)
        for project in resume.projects:
            pieces.append(project.value.name)
            if project.value.description:
                pieces.append(project.value.description)
            pieces.extend(project.value.bullets)
            pieces.extend(project.value.technologies)
        for group in resume.skills:
            pieces.extend(group.value.skills)
        for certification in resume.certifications:
            pieces.append(certification.value.name)

        text = " ".join(pieces)
        numbers = {n.rstrip(".,") for n in _NUMBER_RE.findall(text)}
        words = {w.lower() for w in _WORD_RE.findall(text)} - _STOPWORDS
        return FactIndex(numbers=numbers, words=words)


def check(generated_text: str, index: FactIndex) -> list[FactGuardFinding]:
    """Findings for any number or notable term in ``generated_text`` absent from ``index``."""
    findings: list[FactGuardFinding] = []

    for number in _NUMBER_RE.findall(generated_text):
        cleaned = number.rstrip(".,")
        if cleaned not in index.numbers:
            findings.append(
                FactGuardFinding(
                    message=f'The number "{cleaned}" does not appear anywhere in the original '
                    "content and may have been invented.",
                    token=cleaned,
                )
            )

    for match in _WORD_RE.finditer(generated_text):
        word = match.group(0)
        lowered = word.lower()
        if lowered in _STOPWORDS or lowered in index.words:
            continue
        # A capitalised word is a signal of a proper noun or technology token ("Kubernetes"),
        # except at position 0: English capitalises the first word of a sentence regardless of
        # what it is, so a rewritten bullet's opening verb ("Migrated...") would otherwise flag
        # on every single rewrite - a false positive so constant it would bury real findings.
        is_sentence_initial = match.start() == 0
        looks_like_proper_noun_or_tech = (not is_sentence_initial and word[0].isupper()) or any(
            c.isdigit() or c in "+#" for c in word
        )
        if looks_like_proper_noun_or_tech:
            findings.append(
                FactGuardFinding(
                    message=f'"{word}" does not appear anywhere in the original content and '
                    "may have been invented.",
                    token=word,
                )
            )

    return findings
