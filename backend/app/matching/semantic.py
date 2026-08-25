"""Semantic matching components: project relevance and overall semantic relevance.

Layer 2 (AI_ARCHITECTURE.md section 1) - needs the embedding provider
(``app.matching.embeddings``). When it is unavailable (no package, model failed to load), both
components report ``available=False`` with an explanation naming the missing capability, and the
scoring engine renormalises the remaining weights - the degrade path
``app.analysis.scoring_utils`` built in Phase 3 but never had a component that needed it.
"""

from __future__ import annotations

from app.analysis.models import ComponentScore, Evidence, EvidenceSeverity
from app.analysis.scoring_utils import clamp_score
from app.jobs.models import JobDescription, RequirementImportance
from app.matching.embeddings import EmbeddingProvider, cosine_similarity
from app.resume.models import Resume

#: Empirically (bge-small-en-v1.5), cosine similarity between clearly related professional
#: descriptions clusters around 0.5-0.85, and between unrelated ones around 0.3-0.45. Rescaling
#: onto this observed range spreads scores across 0-100 usefully; without it, everything would
#: compress into a narrow, uninformative band. Documented as a calibration choice, not a law.
_SIMILARITY_FLOOR = 0.30
_SIMILARITY_CEILING = 0.85

_UNAVAILABLE_MESSAGE = (
    "Embeddings are not available on this deployment; this component was excluded from the "
    "overall score and the remaining weights were redistributed."
)


def _rescale(similarity: float) -> float:
    span = _SIMILARITY_CEILING - _SIMILARITY_FLOOR
    return clamp_score((similarity - _SIMILARITY_FLOOR) / span * 100)


def _unavailable(
    key: str, label: str, weight: float, why: str = _UNAVAILABLE_MESSAGE
) -> ComponentScore:
    return ComponentScore(
        key=key,
        label=label,
        score=0.0,
        weight=weight,
        available=False,
        evidence=[Evidence(message=why, severity=EvidenceSeverity.INFO)],
        explanation=(
            f"{label} requires semantic embeddings, which are not available on this deployment."
        ),
    )


def _requirement_text(job: JobDescription) -> str:
    parts = [r.text for r in job.requirements if r.importance != RequirementImportance.OPTIONAL]
    return ". ".join(parts) or job.raw_text


def score_semantic_relevance(
    job: JobDescription, resume: Resume, provider: EmbeddingProvider, weight: float
) -> ComponentScore:
    explanation = (
        "Embeds the resume and the job's requirements text and measures their cosine "
        "similarity, capturing overall thematic fit beyond exact keyword matches."
    )
    if not provider.is_available():
        return _unavailable("semantic_relevance", "Semantic Relevance", weight)

    resume_parts: list[str] = []
    if resume.summary:
        resume_parts.append(resume.summary.value)
    resume_parts.extend(skill for group in resume.skills for skill in group.value.skills)
    resume_parts.extend(bullet for entry in resume.experience for bullet in entry.value.bullets)
    resume_text = ". ".join(resume_parts)
    jd_text = _requirement_text(job)

    if not resume_text.strip() or not jd_text.strip():
        return ComponentScore(
            key="semantic_relevance",
            label="Semantic Relevance",
            score=0.0,
            weight=weight,
            evidence=[
                Evidence(
                    message="Not enough resume or job description content to compare.",
                    severity=EvidenceSeverity.WARNING,
                )
            ],
            explanation=explanation,
        )

    vectors = provider.embed([jd_text, resume_text])
    if vectors is None:
        return _unavailable(
            "semantic_relevance",
            "Semantic Relevance",
            weight,
            "The embedding model could not be run for this request; this component was "
            "excluded from the overall score.",
        )

    similarity = cosine_similarity(vectors[0], vectors[1])
    score = _rescale(similarity)
    return ComponentScore(
        key="semantic_relevance",
        label="Semantic Relevance",
        score=score,
        weight=weight,
        evidence=[
            Evidence(
                message=f"Overall semantic similarity between the resume and the job's "
                f"requirements is {similarity:.2f} (0-1 scale).",
                severity=EvidenceSeverity.POSITIVE if score >= 60 else EvidenceSeverity.INFO,
            )
        ],
        explanation=explanation,
    )


def score_project_relevance(
    job: JobDescription, resume: Resume, provider: EmbeddingProvider, weight: float
) -> ComponentScore:
    explanation = (
        "Embeds each project and the job's requirements text, then scores primarily on the "
        "single most relevant project with partial credit for overall project relevance."
    )
    if not provider.is_available():
        return _unavailable("project_relevance", "Project Relevance", weight)

    if not resume.projects:
        return ComponentScore(
            key="project_relevance",
            label="Project Relevance",
            score=0.0,
            weight=weight,
            evidence=[
                Evidence(
                    message="No projects section was found to compare against the job "
                    "description.",
                    severity=EvidenceSeverity.INFO,
                )
            ],
            explanation=explanation,
        )

    jd_text = _requirement_text(job)
    project_texts: list[str] = []
    for entry in resume.projects:
        parts = [entry.value.name]
        if entry.value.description:
            parts.append(entry.value.description)
        parts.extend(entry.value.bullets)
        parts.extend(entry.value.technologies)
        project_texts.append(". ".join(p for p in parts if p))

    vectors = provider.embed([jd_text, *project_texts])
    if vectors is None:
        return _unavailable(
            "project_relevance",
            "Project Relevance",
            weight,
            "The embedding model could not be run for this request; this component was "
            "excluded from the overall score.",
        )

    jd_vector, *project_vectors = vectors
    similarities = [cosine_similarity(jd_vector, vector) for vector in project_vectors]
    best_index = max(range(len(similarities)), key=lambda i: similarities[i])
    best_score = _rescale(similarities[best_index])
    avg_score = _rescale(sum(similarities) / len(similarities))
    # Mostly reward the single best-matching project; a little credit for breadth of relevance.
    score = clamp_score(0.7 * best_score + 0.3 * avg_score)

    return ComponentScore(
        key="project_relevance",
        label="Project Relevance",
        score=score,
        weight=weight,
        evidence=[
            Evidence(
                message=f'Most relevant project: "{resume.projects[best_index].value.name}" '
                f"(similarity {similarities[best_index]:.2f}).",
                severity=EvidenceSeverity.POSITIVE if best_score >= 60 else EvidenceSeverity.INFO,
            )
        ],
        explanation=explanation,
    )
