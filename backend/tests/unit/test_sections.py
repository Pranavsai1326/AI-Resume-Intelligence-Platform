"""Section detection heuristics."""

from __future__ import annotations

from app.documents.sections import SectionKind, detect_sections
from tests.fixtures import SYNTHETIC_RESUME_TEXT


def test_detects_all_standard_sections_in_the_fixture() -> None:
    sections = detect_sections(SYNTHETIC_RESUME_TEXT)
    kinds = [s.kind for s in sections]
    assert kinds == [
        SectionKind.CONTACT,
        SectionKind.SUMMARY,
        SectionKind.EXPERIENCE,
        SectionKind.EDUCATION,
        SectionKind.SKILLS,
        SectionKind.PROJECTS,
        SectionKind.CERTIFICATIONS,
        SectionKind.CUSTOM,
    ]


def test_contact_preamble_holds_everything_before_the_first_header() -> None:
    sections = detect_sections(SYNTHETIC_RESUME_TEXT)
    contact = sections[0]
    assert contact.kind is SectionKind.CONTACT
    assert "Jordan Ellery Vance" in contact.body
    assert "linkedin.com" in contact.body


def test_known_header_matches_regardless_of_case() -> None:
    for header in ("EXPERIENCE", "experience", "Experience", "Work Experience"):
        sections = detect_sections(f"Name\n\n{header}\nSome content")
        kinds = [s.kind for s in sections]
        assert SectionKind.EXPERIENCE in kinds, header


def test_all_caps_unknown_header_becomes_custom() -> None:
    sections = detect_sections("Name\n\nAWARDS\n- Won something")
    custom = next(s for s in sections if s.kind is SectionKind.CUSTOM)
    assert custom.title == "AWARDS"


def test_ordinary_content_lines_are_not_mistaken_for_headers() -> None:
    """A name and a job title line must not fragment into bogus custom sections.

    This reproduces a real bug found during development: a permissive title-case heuristic
    matched "Jordan Ellery Vance" and "Senior Backend Engineer, Cascade Systems" as headers,
    which corrupted both contact parsing and experience-entry extraction.
    """
    text = (
        "Jordan Ellery Vance\n"
        "jordan.vance@example-fixture.test\n\n"
        "EXPERIENCE\n"
        "Senior Backend Engineer, Cascade Systems\n"
        "- Did the work\n"
    )
    sections = detect_sections(text)
    kinds = [s.kind for s in sections]
    assert kinds == [SectionKind.CONTACT, SectionKind.EXPERIENCE]
    assert "Senior Backend Engineer, Cascade Systems" in sections[1].body


def test_no_headers_at_all_yields_a_single_contact_block() -> None:
    sections = detect_sections("Just some plain text\nwith no structure at all")
    assert len(sections) == 1
    assert sections[0].kind is SectionKind.CONTACT


def test_empty_text_yields_no_sections() -> None:
    assert detect_sections("") == []
    assert detect_sections("   \n  \n") == []


def test_header_immediately_at_the_start_produces_no_preamble() -> None:
    sections = detect_sections("EXPERIENCE\nSome content")
    assert sections[0].kind is SectionKind.EXPERIENCE
    assert not any(s.kind is SectionKind.CONTACT for s in sections)


def test_section_body_stops_at_the_next_header() -> None:
    sections = detect_sections("EXPERIENCE\nline one\nline two\nEDUCATION\nline three")
    experience = next(s for s in sections if s.kind is SectionKind.EXPERIENCE)
    assert "line three" not in experience.body
    assert "line one" in experience.body and "line two" in experience.body
