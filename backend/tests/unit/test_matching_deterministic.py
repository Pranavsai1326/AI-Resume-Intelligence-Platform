"""Deterministic matching components: required/preferred skills, experience, education."""

from __future__ import annotations

from app.analysis.models import EvidenceSeverity
from app.documents.structure import build_resume
from app.jobs.models import EducationLevel
from app.jobs.parse import parse_job_description
from app.matching.deterministic import (
    highest_education_level,
    score_education,
    score_experience,
    score_preferred_skills,
    score_required_skills,
    total_years_experience,
)

RESUME_TEXT = """Jordan Ellery Vance

EXPERIENCE
Senior Backend Engineer, Cascade Systems
Jan 2021 - Present
- Led migration to Kubernetes

Software Engineer | Northlight Data
Jun 2018 - Dec 2020
- Built the ingestion service using Python

EDUCATION
University of Riverbend, Bachelor of Science in Computer Science
2014 - 2018

SKILLS
Languages: Python, Go
Infrastructure: Kubernetes, AWS
"""

JD_TEXT = """Requirements
- 5+ years of experience
- Bachelor degree in Computer Science
- Proficiency in Python
- Experience with Kubernetes

Preferred Qualifications
- Experience with Terraform
"""


def resume():
    return build_resume(RESUME_TEXT)


def job():
    return parse_job_description(JD_TEXT)


class TestRequiredSkills:
    def test_all_matched_scores_100(self) -> None:
        result = score_required_skills(job(), resume(), weight=0.4)
        assert result.score == 100.0
        assert result.weight == 0.4
        assert all(e.severity == EvidenceSeverity.POSITIVE for e in result.evidence)

    def test_missing_required_skill_lowers_score(self) -> None:
        jd = parse_job_description("Requirements\n- Proficiency in Python\n- Proficiency in Rust\n")
        result = score_required_skills(jd, resume(), weight=0.4)
        assert result.score == 50.0
        assert any(e.severity == EvidenceSeverity.WARNING for e in result.evidence)

    def test_no_requirements_scores_100_with_info_evidence(self) -> None:
        jd = parse_job_description("Responsibilities\n- Build things\n")
        result = score_required_skills(jd, resume(), weight=0.4)
        assert result.score == 100.0
        assert result.evidence[0].severity == EvidenceSeverity.INFO

    def test_unrecognized_skill_term_is_unverifiable_not_a_failure(self) -> None:
        jd = parse_job_description("Requirements\n- Experience with QuantumFluxToolkit\n")
        result = score_required_skills(jd, resume(), weight=0.4)
        assert result.score == 50.0
        assert "could not be automatically verified" in result.evidence[0].message


class TestPreferredSkills:
    def test_partially_matched(self) -> None:
        result = score_preferred_skills(job(), resume(), weight=0.15)
        # "Experience with Terraform" is the only preferred requirement and is not in the resume.
        assert result.score == 0.0


class TestExperience:
    def test_meets_requirement(self) -> None:
        result = score_experience(job(), resume(), weight=0.2)
        assert result.score == 100.0
        assert result.evidence[0].severity == EvidenceSeverity.POSITIVE

    def test_falls_short_of_requirement(self) -> None:
        jd = parse_job_description("Requirements\n- 20+ years of experience\n")
        result = score_experience(jd, resume(), weight=0.2)
        assert 0 < result.score < 100
        assert result.evidence[0].severity == EvidenceSeverity.WARNING

    def test_no_requirement_specified_scores_100(self) -> None:
        jd = parse_job_description("Responsibilities\n- Build things\n")
        result = score_experience(jd, resume(), weight=0.2)
        assert result.score == 100.0


class TestEducation:
    def test_meets_requirement(self) -> None:
        result = score_education(job(), resume(), weight=0.05)
        assert result.score == 100.0

    def test_below_requirement(self) -> None:
        jd = parse_job_description("Requirements\n- PhD required\n")
        result = score_education(jd, resume(), weight=0.05)
        assert result.score < 100.0
        assert result.evidence[0].severity == EvidenceSeverity.WARNING

    def test_no_requirement_specified_scores_100(self) -> None:
        jd = parse_job_description("Responsibilities\n- Build things\n")
        result = score_education(jd, resume(), weight=0.05)
        assert result.score == 100.0


def test_total_years_experience_sums_role_durations() -> None:
    from datetime import date

    years = total_years_experience(resume(), today=date(2024, 6, 1))
    # Jan 2021 -> Jun 2024 (~3.4y) + Jun 2018 -> Dec 2020 (~2.5y)
    assert 5.5 < years < 6.2


def test_total_years_experience_empty_resume() -> None:
    from app.resume.models import Resume

    assert total_years_experience(Resume()) == 0.0


def test_highest_education_level_picks_the_best_across_entries() -> None:
    # Blank-line separated, as most resumes do. The no-blank-line, no-bullets case (which used to
    # collapse two education entries into one) is covered directly by
    # tests/unit/test_structure.py::test_education_entries_without_blank_line_still_split.
    text = (
        "EDUCATION\n"
        "State University, Associate Degree\n2010 - 2012\n\n"
        "University of Riverbend, Master of Science in Computer Science\n2012 - 2014\n"
    )
    level = highest_education_level(build_resume(text))
    assert level == EducationLevel.MASTER


def test_highest_education_level_none_when_no_education() -> None:
    from app.resume.models import Resume

    assert highest_education_level(Resume()) == EducationLevel.NONE
