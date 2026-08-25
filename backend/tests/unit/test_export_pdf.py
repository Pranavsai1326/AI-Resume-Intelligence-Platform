"""Unit tests for app.export.pdf.

Requires Playwright's Chromium browser to be installed in the venv; skips with a clear reason
when it is not, rather than failing the whole suite on a missing optional dependency.
"""

from __future__ import annotations

import pytest

from app.export.pdf import render_resume_pdf
from tests.fixtures import make_resume

try:
    import playwright  # noqa: F401

    _PLAYWRIGHT_INSTALLED = True
except ImportError:
    _PLAYWRIGHT_INSTALLED = False

pytestmark = pytest.mark.skipif(
    not _PLAYWRIGHT_INSTALLED, reason="playwright is not installed in this environment"
)


async def test_render_resume_pdf_produces_nonempty_pdf_bytes() -> None:
    data = await render_resume_pdf(make_resume())
    if data is None:
        pytest.skip("Chromium is not installed for Playwright in this environment")
    assert isinstance(data, bytes)
    assert data.startswith(b"%PDF")
    assert len(data) > 100
