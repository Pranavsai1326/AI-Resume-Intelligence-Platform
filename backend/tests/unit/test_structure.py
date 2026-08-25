"""Building a structured, provenance-tagged Resume from extracted text."""

from __future__ import annotations

from app.documents.structure import build_resume, parse_date_range
from app.resume.provenance import ProvenanceKind
from tests.fixtures import SYNTHETIC_RESUME_TEXT


def test_full_fixture_extracts_every_section() -> None:
    resume = build_resume(SYNTHETIC_RESUME_TEXT)

    assert resume.contact.full_name is not None
    assert resume.contact.full_name.value == "Jordan Ellery Vance"
    assert resume.contact.email is not None
    assert resume.contact.email.value == "jordan.vance@example-fixture.test"
    assert resume.contact.phone is not None
    assert resume.contact.location is not None
    assert resume.contact.location.value == "San Francisco, CA"
    assert len(resume.contact.links) == 1

    assert resume.summary is not None
    assert "Backend engineer" in resume.summary.value

    assert len(resume.experience) == 2
    assert resume.experience[0].value.title == "Senior Backend Engineer"
    assert resume.experience[0].value.organization == "Cascade Systems"
    assert resume.experience[0].value.dates is not None
    assert resume.experience[0].value.dates.is_current is True
    assert len(resume.experience[0].value.bullets) == 2

    assert len(resume.education) == 1
    assert resume.education[0].value.institution == "University of Riverbend"
    assert resume.education[0].value.degree == "B.S. Computer Science"

    assert len(resume.skills) == 2
    categories = {g.value.category for g in resume.skills}
    assert categories == {"Languages", "Infrastructure"}

    assert len(resume.projects) == 1
    assert resume.projects[0].value.name == "Trailmark"
    assert resume.projects[0].value.technologies == ["Python", "FastAPI"]

    assert len(resume.certifications) == 1
    assert resume.certifications[0].value.issuer == "Amazon"
    assert resume.certifications[0].value.date == "2022"

    assert len(resume.custom_sections) == 1
    assert resume.custom_sections[0].value.title == "AWARDS"


def test_every_populated_field_is_marked_extracted() -> None:
    """Structure building is Layer 1 (deterministic) - nothing here may claim AI provenance."""
    resume = build_resume(SYNTHETIC_RESUME_TEXT)
    assert resume.contact.full_name.provenance.kind is ProvenanceKind.EXTRACTED
    assert resume.summary.provenance.kind is ProvenanceKind.EXTRACTED
    assert resume.experience[0].provenance.kind is ProvenanceKind.EXTRACTED
    assert resume.experience[0].provenance.confidence is not None


def test_pdf_style_text_without_blank_lines_still_splits_into_entries() -> None:
    """Reproduces a real bug: PDF extraction collapses blank lines, which broke multi-entry
    sections until the entry splitter gained a bullet-boundary fallback."""
    text = (
        "Name\n\n"
        "EXPERIENCE\n"
        "Senior Backend Engineer, Cascade Systems\n"
        "Jan 2021 - Present\n"
        "- Led migration of the billing pipeline\n"
        "- Reduced latency significantly\n"
        "Software Engineer | Northlight Data\n"
        "Jun 2018 - Dec 2020\n"
        "- Built the ingestion service from scratch\n"
    )
    resume = build_resume(text)
    assert len(resume.experience) == 2
    assert resume.experience[0].value.title == "Senior Backend Engineer"
    assert resume.experience[1].value.title == "Software Engineer"
    assert resume.experience[0].value.bullets == [
        "Led migration of the billing pipeline",
        "Reduced latency significantly",
    ]


def test_title_and_organization_on_separate_lines_are_both_captured() -> None:
    """Phase 9C regression: a common real-world template puts the job title, organisation, and
    date range on three entirely separate lines rather than "Title, Org" on one. Before the fix,
    the organisation was silently dropped (left empty) and both the organisation name and the
    date range were misfiled as fake bullets instead."""
    text = (
        "EXPERIENCE\n"
        "Senior Backend Engineer\n"
        "Cascade Systems\n"
        "Jan 2021 - Present\n"
        "- Migrated the billing pipeline to event sourcing\n"
        "- Reduced latency by tuning the query planner\n"
    )
    resume = build_resume(text)
    assert len(resume.experience) == 1
    entry = resume.experience[0].value
    assert entry.title == "Senior Backend Engineer"
    assert entry.organization == "Cascade Systems"
    assert entry.dates is not None
    assert entry.dates.is_current is True
    assert entry.bullets == [
        "Migrated the billing pipeline to event sourcing",
        "Reduced latency by tuning the query planner",
    ]


def test_project_single_description_line_is_not_mistaken_for_a_separate_header_line() -> None:
    """The three-separate-lines fix above must not swallow a project's one-line description into
    the header - projects deliberately keep that line available as `description`
    (`merge_subheader=False` in `_parse_projects`), since a lone content line here is common and
    correctly belongs to `description`/`bullets`, not to a title/organisation split."""
    text = "PROJECTS\nSide Project\nA single-line description of the project\n"
    resume = build_resume(text)
    assert len(resume.projects) == 1
    assert resume.projects[0].value.name == "Side Project"
    assert resume.projects[0].value.description == "A single-line description of the project"


def test_short_degree_acronym_does_not_truncate_the_education_entry() -> None:
    """Phase 9C regression: a full end-to-end reproduction of the "MBA" section-detection bug -
    before the fix, this entry's degree and dates were silently lost entirely because "MBA" alone
    on its own line was misread as a new section header."""
    text = (
        "EDUCATION\n"
        "State University\n"
        "Bachelor of Science in Computer Science\n"
        "2015 - 2019\n"
        "\n"
        "Tech Institute\n"
        "MBA\n"
        "2020 - 2022\n"
    )
    resume = build_resume(text)
    assert len(resume.education) == 2
    assert resume.education[1].value.institution == "Tech Institute"
    assert resume.education[1].value.degree == "MBA"
    assert resume.education[1].value.dates is not None
    assert resume.education[1].value.dates.raw == "2020 - 2022"


def test_education_entries_without_blank_line_still_split() -> None:
    """Regression for a gap noted since Phase 2 and fixed in Phase 6: education entries have no
    bullets, so the experience/project entry-splitter's bullet-boundary fallback had nothing to
    anchor on and two entries in a row silently merged into one. A degree line ("B.S. ...") is
    education's equivalent anchor - it closes out the entry it belongs to."""
    text = (
        "EDUCATION\n"
        "State University, B.S. Computer Science\n"
        "2011 - 2015\n"
        "Example College, M.S. Data Science\n"
        "2016 - 2018\n"
    )
    resume = build_resume(text)
    assert len(resume.education) == 2
    assert resume.education[0].value.institution == "State University"
    assert resume.education[0].value.degree == "B.S. Computer Science"
    assert resume.education[1].value.institution == "Example College"
    assert resume.education[1].value.degree == "M.S. Data Science"


def test_single_education_entry_without_degree_keyword_is_not_split() -> None:
    """A safe-failure check: an entry with no recognised degree keyword is left as one block
    rather than risked being split on the wrong line."""
    resume = build_resume("EDUCATION\nSelf-Taught Institute\nIndependent study, 2020\n")
    assert len(resume.education) == 1


def test_does_not_fabricate_missing_contact_fields() -> None:
    resume = build_resume("EXPERIENCE\nSomething, Somewhere\n- did stuff")
    assert resume.contact.full_name is None
    assert resume.contact.email is None
    assert resume.contact.phone is None


def test_empty_text_produces_an_empty_but_valid_resume() -> None:
    resume = build_resume("")
    assert resume.contact.full_name is None
    assert resume.experience == []
    assert resume.summary is None


def test_flat_skills_section_without_categories() -> None:
    resume = build_resume("SKILLS\nPython, Go, Rust, SQL\n")
    assert len(resume.skills) == 1
    assert resume.skills[0].value.category is None
    assert resume.skills[0].value.skills == ["Python", "Go", "Rust", "SQL"]


def test_ungrouped_and_grouped_skills_do_not_both_appear() -> None:
    resume = build_resume("SKILLS\nLanguages: Python, Go\n")
    assert len(resume.skills) == 1
    assert resume.skills[0].value.category == "Languages"


class TestParseDateRange:
    def test_month_name_range(self) -> None:
        dates = parse_date_range("Jan 2020 - Mar 2021")
        assert dates is not None
        assert dates.start == "2020-01"
        assert dates.end == "2021-03"
        assert dates.is_current is False

    def test_present_is_marked_current_with_no_end(self) -> None:
        dates = parse_date_range("March 2022 - Present")
        assert dates is not None
        assert dates.end is None
        assert dates.is_current is True

    def test_slash_dates(self) -> None:
        dates = parse_date_range("03/2020 - 06/2022")
        assert dates is not None
        assert dates.start == "2020-03"
        assert dates.end == "2022-06"

    def test_bare_years_are_not_padded_with_a_fabricated_month(self) -> None:
        dates = parse_date_range("2019 - 2021")
        assert dates is not None
        assert dates.start == "2019"
        assert dates.end == "2021"

    def test_no_date_present_returns_none(self) -> None:
        assert parse_date_range("Just a regular sentence with no dates") is None

    def test_en_dash_and_em_dash_separators(self) -> None:
        assert parse_date_range("2019 – 2021") is not None
        assert parse_date_range("2019 — 2021") is not None
