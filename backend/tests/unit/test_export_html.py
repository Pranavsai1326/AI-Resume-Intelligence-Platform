"""Unit tests for app.export.html_template."""

from __future__ import annotations

from app.export.html_template import build_resume_html
from app.resume.models import ExperienceEntry
from app.resume.provenance import Provenance, ProvenancedValue
from tests.fixtures import make_resume


def test_build_resume_html_includes_name_and_sections() -> None:
    html = build_resume_html(make_resume())
    assert "Jordan Ellery Vance" in html
    assert "<h2>Experience</h2>" in html
    assert "<h2>Skills</h2>" in html
    assert "Cascade Systems" in html


def test_build_resume_html_escapes_script_tags_in_bullets() -> None:
    resume = make_resume()
    resume.experience.append(
        ProvenancedValue(
            value=ExperienceEntry(
                title="Engineer",
                organization="Evil Corp",
                bullets=["<script>alert('xss')</script>"],
            ),
            provenance=Provenance.extracted(confidence=0.9),
        )
    )
    html = build_resume_html(resume)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_build_resume_html_escapes_malicious_name() -> None:
    resume = make_resume()
    resume.contact.full_name = ProvenancedValue(
        value="<img src=x onerror=alert(1)>", provenance=Provenance.user_provided()
    )
    html = build_resume_html(resume)
    assert "<img src=x" not in html
    assert "&lt;img" in html


def test_build_resume_html_handles_empty_resume() -> None:
    from app.resume.models import Resume

    html = build_resume_html(Resume())
    assert "<h1>Resume</h1>" in html
    assert "<!doctype html>" in html
