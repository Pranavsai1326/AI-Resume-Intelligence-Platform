"""HTML resume template - the shared source for both the PDF export and (later) live preview.

Deliberately one clean, ATS-conscious template for now (single column, no tables, no text
boxes, no images) rather than the several PRD section 10 eventually calls for - PROJECT_STATUS.md
tracks the rest as follow-up work, not silently promised here.

All user content is escaped with ``html.escape`` (SECURITY.md section 6): a resume is untrusted
input that happens to render as a document, not markup to trust.
"""

from __future__ import annotations

from html import escape

from app.resume.models import Resume

_STYLE = """
  @page { margin: 0.6in; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    color: #1a1a1a;
    font-size: 10.5pt;
    line-height: 1.45;
  }
  h1 { font-size: 20pt; margin: 0 0 2pt 0; }
  .contact { font-size: 9.5pt; color: #444; margin-bottom: 14pt; }
  .contact span:not(:last-child)::after { content: " \\2022 "; color: #999; }
  h2 {
    font-size: 11pt;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid #ccc;
    margin: 16pt 0 6pt 0;
    padding-bottom: 2pt;
  }
  .entry { margin-bottom: 10pt; }
  .entry-header { display: flex; justify-content: space-between; font-weight: 600; }
  .entry-sub {
    display: flex; justify-content: space-between;
    font-style: italic; color: #444; font-size: 9.5pt;
  }
  ul { margin: 4pt 0 0 0; padding-left: 16pt; }
  li { margin-bottom: 2pt; }
  .skill-group { margin-bottom: 4pt; }
  .skill-group .category { font-weight: 600; }
"""


def _contact_line(resume: Resume) -> str:
    parts: list[str] = []
    if resume.contact.email:
        parts.append(escape(resume.contact.email.value))
    if resume.contact.phone:
        parts.append(escape(resume.contact.phone.value))
    if resume.contact.location:
        parts.append(escape(resume.contact.location.value))
    for link in resume.contact.links:
        parts.append(escape(link.value))
    if not parts:
        return ""
    spans = "".join(f"<span>{part}</span>" for part in parts)
    return f'<p class="contact">{spans}</p>'


def _experience_section(resume: Resume) -> str:
    if not resume.experience:
        return ""
    entries = []
    for item in resume.experience:
        entry = item.value
        dates = escape(entry.dates.raw) if entry.dates else ""
        bullets = "".join(f"<li>{escape(b)}</li>" for b in entry.bullets)
        bullets_html = f"<ul>{bullets}</ul>" if bullets else ""
        header = f"{escape(entry.title)}</span><span>{dates}"
        entries.append(
            f'<div class="entry">'
            f'<div class="entry-header"><span>{header}</span></div>'
            f'<div class="entry-sub"><span>{escape(entry.organization)}</span>'
            f'<span>{escape(entry.location or "")}</span></div>'
            f"{bullets_html}"
            f"</div>"
        )
    return f"<h2>Experience</h2>{''.join(entries)}"


def _education_section(resume: Resume) -> str:
    if not resume.education:
        return ""
    entries = []
    for item in resume.education:
        entry = item.value
        dates = escape(entry.dates.raw) if entry.dates else ""
        degree = escape(entry.degree) if entry.degree else ""
        details = "".join(f"<li>{escape(d)}</li>" for d in entry.details)
        details_html = f"<ul>{details}</ul>" if details else ""
        header = f"{escape(entry.institution)}</span><span>{dates}"
        entries.append(
            f'<div class="entry">'
            f'<div class="entry-header"><span>{header}</span></div>'
            f'<div class="entry-sub"><span>{degree}</span></div>'
            f"{details_html}"
            f"</div>"
        )
    return f"<h2>Education</h2>{''.join(entries)}"


def _skills_section(resume: Resume) -> str:
    if not resume.skills:
        return ""
    groups = []
    for item in resume.skills:
        group = item.value
        skills = escape(", ".join(group.skills))
        if group.category:
            category = escape(group.category)
            groups.append(
                f'<p class="skill-group"><span class="category">{category}:</span> {skills}</p>'
            )
        else:
            groups.append(f'<p class="skill-group">{skills}</p>')
    return f"<h2>Skills</h2>{''.join(groups)}"


def _projects_section(resume: Resume) -> str:
    if not resume.projects:
        return ""
    entries = []
    for item in resume.projects:
        entry = item.value
        tech = escape(", ".join(entry.technologies)) if entry.technologies else ""
        header = escape(entry.name) + (f" ({tech})" if tech else "")
        description = f"<p>{escape(entry.description)}</p>" if entry.description else ""
        bullets = "".join(f"<li>{escape(b)}</li>" for b in entry.bullets)
        bullets_html = f"<ul>{bullets}</ul>" if bullets else ""
        entries.append(
            f'<div class="entry"><div class="entry-header">{header}</div>'
            f"{description}{bullets_html}</div>"
        )
    return f"<h2>Projects</h2>{''.join(entries)}"


def _certifications_section(resume: Resume) -> str:
    if not resume.certifications:
        return ""
    items = []
    for item in resume.certifications:
        entry = item.value
        bits = [escape(entry.name)]
        if entry.issuer:
            bits.append(escape(entry.issuer))
        if entry.date:
            bits.append(escape(entry.date))
        items.append(f"<li>{' — '.join(bits)}</li>")
    return f"<h2>Certifications</h2><ul>{''.join(items)}</ul>"


def _custom_sections(resume: Resume) -> str:
    blocks = []
    for item in resume.custom_sections:
        entry = item.value
        bullets = "".join(f"<li>{escape(b)}</li>" for b in entry.bullets)
        blocks.append(f"<h2>{escape(entry.title)}</h2><ul>{bullets}</ul>")
    return "".join(blocks)


def build_resume_html(resume: Resume) -> str:
    name = escape(resume.contact.full_name.value) if resume.contact.full_name else "Resume"
    summary = f"<p>{escape(resume.summary.value)}</p>" if resume.summary else ""

    body = "".join(
        [
            f"<h1>{name}</h1>",
            _contact_line(resume),
            summary,
            _experience_section(resume),
            _education_section(resume),
            _skills_section(resume),
            _projects_section(resume),
            _certifications_section(resume),
            _custom_sections(resume),
        ]
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_STYLE}</style></head><body>{body}</body></html>"
    )
