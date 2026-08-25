"""Job description parsing: sections, title extraction, requirement classification."""

from __future__ import annotations

from app.jobs.models import EducationLevel, RequirementImportance, RequirementKind
from app.jobs.parse import classify_requirement, parse_job_description

SYNTHETIC_JD_TEXT = """Senior Backend Engineer

About the role
We are looking for a Senior Backend Engineer to join our platform team.

Requirements
- 5+ years of experience building backend systems
- Bachelor's degree in Computer Science or related field
- Proficiency in Python and Go
- Experience with Kubernetes and AWS
- Strong communication skills

Preferred Qualifications
- Experience with Terraform
- AWS Certified Solutions Architect

Responsibilities
- Design and build scalable backend services
- Mentor junior engineers
- Participate in on-call rotation

Benefits
- Competitive salary
- Health insurance
"""


def test_extracts_title() -> None:
    jd = parse_job_description(SYNTHETIC_JD_TEXT)
    assert jd.title == "Senior Backend Engineer"


def test_required_and_preferred_requirements_are_separated() -> None:
    jd = parse_job_description(SYNTHETIC_JD_TEXT)
    required = jd.by_importance(RequirementImportance.REQUIRED)
    preferred = jd.by_importance(RequirementImportance.PREFERRED)
    assert any("5+ years" in r.text for r in required)
    assert any("Terraform" in r.text for r in preferred)
    assert not any("Terraform" in r.text for r in required)


def test_experience_requirement_extracts_years() -> None:
    jd = parse_job_description(SYNTHETIC_JD_TEXT)
    experience_reqs = jd.by_kind(RequirementKind.EXPERIENCE)
    assert len(experience_reqs) == 1
    assert experience_reqs[0].min_years == 5.0
    assert experience_reqs[0].importance == RequirementImportance.REQUIRED


def test_education_requirement_extracts_level() -> None:
    jd = parse_job_description(SYNTHETIC_JD_TEXT)
    education_reqs = jd.by_kind(RequirementKind.EDUCATION)
    assert len(education_reqs) == 1
    assert education_reqs[0].education_level == EducationLevel.BACHELOR


def test_skill_requirements_extract_recognized_keywords() -> None:
    jd = parse_job_description(SYNTHETIC_JD_TEXT)
    skill_reqs = jd.by_kind(RequirementKind.SKILL)
    all_keywords = {kw for r in skill_reqs for kw in r.keywords}
    assert "python" in all_keywords
    assert "go" in all_keywords
    assert "kubernetes" in all_keywords
    assert "aws" in all_keywords


def test_soft_skill_requirement_is_classified_separately_from_technical() -> None:
    jd = parse_job_description(SYNTHETIC_JD_TEXT)
    soft_skill_reqs = jd.by_kind(RequirementKind.SOFT_SKILL)
    assert any("communication" in r.keywords for r in soft_skill_reqs)


def test_certification_requirement_is_classified() -> None:
    jd = parse_job_description(SYNTHETIC_JD_TEXT)
    cert_reqs = jd.by_kind(RequirementKind.CERTIFICATION)
    assert any("AWS Certified" in r.text for r in cert_reqs)


def test_responsibilities_are_kept_but_not_treated_as_requirements_to_match() -> None:
    jd = parse_job_description(SYNTHETIC_JD_TEXT)
    assert "Mentor junior engineers" in jd.responsibilities
    responsibility_reqs = jd.by_kind(RequirementKind.RESPONSIBILITY)
    assert all(r.importance == RequirementImportance.OPTIONAL for r in responsibility_reqs)


def test_benefits_section_is_ignored() -> None:
    jd = parse_job_description(SYNTHETIC_JD_TEXT)
    all_text = " ".join(r.text for r in jd.requirements)
    assert "Competitive salary" not in all_text
    assert "Health insurance" not in all_text


def test_short_single_word_skill_does_not_false_positive_inside_other_words() -> None:
    """Reproduces a real bug: naive substring matching made "r" match inside "your"/"were" and
    "go" match inside "google" - fixed via word-boundary matching in app.analysis.taxonomy."""
    jd = parse_job_description("Requirements\n- Strong communication skills\n")
    skill_reqs = jd.by_kind(RequirementKind.SKILL) + jd.by_kind(RequirementKind.SOFT_SKILL)
    all_keywords = {kw for r in skill_reqs for kw in r.keywords}
    assert "r" not in all_keywords
    assert "go" not in all_keywords


def test_empty_jd_produces_no_requirements() -> None:
    jd = parse_job_description("")
    assert jd.requirements == []
    assert jd.title is None


def test_jd_with_no_sections_at_all() -> None:
    jd = parse_job_description("Just a plain paragraph with no structure.")
    assert jd.requirements == []


class TestClassifyRequirement:
    def test_years_pattern_takes_priority_over_skill_matching(self) -> None:
        req = classify_requirement("3+ years of Python experience", RequirementImportance.REQUIRED)
        assert req.kind == RequirementKind.EXPERIENCE
        assert req.min_years == 3.0

    def test_unrecognized_text_falls_back_to_plain_skill_not_dropped(self) -> None:
        req = classify_requirement(
            "Experience with QuantumFluxToolkit", RequirementImportance.REQUIRED
        )
        assert req.kind == RequirementKind.SKILL
        assert req.keywords == []
        assert "QuantumFluxToolkit" in req.text

    def test_master_degree_pattern(self) -> None:
        req = classify_requirement("Master's degree required", RequirementImportance.REQUIRED)
        assert req.kind == RequirementKind.EDUCATION
        assert req.education_level == EducationLevel.MASTER

    def test_phd_pattern(self) -> None:
        req = classify_requirement("PhD in a related field", RequirementImportance.PREFERRED)
        assert req.kind == RequirementKind.EDUCATION
        assert req.education_level == EducationLevel.PHD
