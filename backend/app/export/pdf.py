"""PDF export via headless Chromium (ADR-0006).

Launches a fresh, offline browser context per render rather than pooling one - simpler and safer
for a first implementation; a persistent pool is a reasonable later optimisation if export volume
ever makes the few-hundred-millisecond launch overhead matter. The page only ever receives
content via ``set_content`` (never ``goto``), so there is no URL for the sandboxed, offline
context to fetch in the first place (SECURITY.md section 6).
"""

from __future__ import annotations

from app.export.html_template import build_resume_html
from app.logging import get_logger
from app.resume.models import Resume

logger = get_logger(__name__)

RENDER_TIMEOUT_MS = 15_000


async def render_resume_pdf(resume: Resume) -> bytes | None:
    """Render ``resume`` to PDF bytes, or ``None`` if Chromium is unavailable or rendering fails."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None

    html = build_resume_html(resume)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=["--disable-extensions"])
            try:
                context = await browser.new_context(offline=True)
                page = await context.new_page()
                await page.set_content(html, timeout=RENDER_TIMEOUT_MS)
                return await page.pdf(
                    format="Letter",
                    print_background=True,
                    margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                )
            finally:
                await browser.close()
    except Exception:
        logger.warning("export.pdf_render_failed")
        return None
