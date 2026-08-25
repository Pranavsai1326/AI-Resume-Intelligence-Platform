"""Each scoring component in isolation: known-good and known-bad inputs land in expected bands."""

from __future__ import annotations

from app.analysis.ats import score_ats_compatibility
from app.analysis.content_quality import score_content_quality
from app.analysis.experience_quality import score_experience_quality
from app.analysis.formatting import score_formatting
from app.analysis.impact import score_impact
from app.analysis.models import EvidenceSeverity
from app.analysis.skills_coverage import score_skills_coverage
from app.documents.extract.base import LayoutSignals
from app.documents.structure import build_resume
from app.resume.models import Resume

STRONG_RESUME_TEXT = """Jordan Ellery Vance
jordan.vance@example-fixture.test | (415) 555-0139

SUMMARY
Backend engineer with 6 years building distributed systems.

EXPERIENCE
Senior Backend Engineer, Cascade Systems
Jan 2021 - Present
- Led migration of the billing pipeline, cutting incident volume by 40%
- Reduced p99 latency by 25% through query planner tuning
- Mentored 3 junior engineers

Software Engineer | Northlight Data
Jun 2018 - Dec 2020
- Built the ingestion service, processing 2M events per day

EDUCATION
University of Riverbend, B.S. Computer Science
2014 - 2018

SKILLS
Languages: Python, Go, TypeScript
Infrastructure: Kubernetes, Terraform, AWS

PROJECTS
Trailmark (Python, FastAPI)
- Open source resume parser used by 200 developers
"""

WEAK_RESUME_TEXT = """EXPERIENCE
Engineer at SomeCorp
I was responsible for helping with stuff.
"""

CLEAN_LAYOUT = LayoutSignals(page_count=1)
RISKY_LAYOUT = LayoutSignals(
    page_count=5,
    multi_column=True,
    has_tables=True,
    has_images=True,
    has_text_boxes=True,
    has_repeating_header_footer=True,
)


def strong_resume() -> Resume:
    return build_resume(STRONG_RESUME_TEXT)


def weak_resume() -> Resume:
    return build_resume(WEAK_RESUME_TEXT)


class TestAtsCompatibility:
    def test_strong_resume_scores_high(self) -> None:
        result = score_ats_compatibility(strong_resume(), CLEAN_LAYOUT, weight=0.2)
        assert result.score >= 90
        assert result.weight == 0.2
        assert any(e.severity == EvidenceSeverity.POSITIVE for e in result.evidence)

    def test_risky_layout_scores_low(self) -> None:
        result = score_ats_compatibility(weak_resume(), RISKY_LAYOUT, weight=0.2)
        assert result.score < 40
        warnings = [e for e in result.evidence if e.severity == EvidenceSeverity.WARNING]
        assert any("multiple columns" in w.message for w in warnings)
        assert any("table" in w.message for w in warnings)

    def test_every_component_has_an_explanation(self) -> None:
        result = score_ats_compatibility(strong_resume(), CLEAN_LAYOUT, weight=0.2)
        assert result.explanation
        assert result.key == "ats_compatibility"
        assert result.label == "ATS Compatibility"

    def test_score_never_leaves_the_0_100_range(self) -> None:
        result = score_ats_compatibility(Resume(), RISKY_LAYOUT, weight=0.2)
        assert 0.0 <= result.score <= 100.0


class TestFormatting:
    def test_strong_resume_scores_high(self) -> None:
        result = score_formatting(strong_resume(), CLEAN_LAYOUT, weight=0.15)
        assert result.score >= 85

    def test_missing_sections_are_penalized(self) -> None:
        result = score_formatting(weak_resume(), CLEAN_LAYOUT, weight=0.15)
        assert result.score <= 60

    def test_long_document_is_flagged(self) -> None:
        long_layout = LayoutSignals(page_count=6)
        short_layout = LayoutSignals(page_count=1)
        long_result = score_formatting(strong_resume(), long_layout, weight=0.15)
        short_result = score_formatting(strong_resume(), short_layout, weight=0.15)
        assert long_result.score < short_result.score

    def test_docx_with_no_page_count_is_not_penalized_for_length(self) -> None:
        no_page_layout = LayoutSignals(page_count=None)
        result = score_formatting(strong_resume(), no_page_layout, weight=0.15)
        assert not any("page" in e.message.lower() for e in result.evidence)


class TestContentQuality:
    def test_strong_bullets_score_high(self) -> None:
        result = score_content_quality(strong_resume(), weight=0.2)
        assert result.score >= 80

    def test_weak_phrasing_is_penalized(self) -> None:
        result = score_content_quality(weak_resume(), weight=0.2)
        assert result.score < 50

    def test_no_bullets_scores_zero_not_a_crash(self) -> None:
        result = score_content_quality(Resume(), weight=0.2)
        assert result.score == 0.0
        assert result.evidence


class TestSkillsCoverage:
    def test_categorized_skills_score_high(self) -> None:
        result = score_skills_coverage(strong_resume(), weight=0.15)
        assert result.score >= 70

    def test_missing_skills_section_scores_zero(self) -> None:
        result = score_skills_coverage(weak_resume(), weight=0.15)
        assert result.score == 0.0

    def test_unrecognized_skill_is_not_penalized(self) -> None:
        """A niche or uncommon skill must never be marked down for absence from the taxonomy."""
        resume = build_resume("SKILLS\nQuantumFluxToolkit, NicheFramework9000\n")
        result = score_skills_coverage(resume, weight=0.15)
        assert not any(e.severity == EvidenceSeverity.WARNING for e in result.evidence)


class TestExperienceQuality:
    def test_detailed_experience_scores_high(self) -> None:
        result = score_experience_quality(strong_resume(), weight=0.2)
        assert result.score >= 75

    def test_sparse_experience_scores_low(self) -> None:
        result = score_experience_quality(weak_resume(), weight=0.2)
        assert result.score < 50

    def test_no_experience_scores_zero(self) -> None:
        result = score_experience_quality(Resume(), weight=0.2)
        assert result.score == 0.0


class TestImpact:
    def test_quantified_outcome_driven_resume_scores_high(self) -> None:
        result = score_impact(strong_resume(), weight=0.1)
        assert result.score >= 70

    def test_unquantified_resume_scores_low(self) -> None:
        result = score_impact(weak_resume(), weight=0.1)
        assert result.score < 30

    def test_no_bullets_scores_zero(self) -> None:
        result = score_impact(Resume(), weight=0.1)
        assert result.score == 0.0
