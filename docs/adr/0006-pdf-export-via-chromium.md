# ADR-0006: Resume and report PDFs rendered by headless Chromium

Status: Accepted (2026-08-22)

## Context
Resume templates must look identical in the live preview and the exported PDF, and exported PDFs
must remain ATS-parseable (selectable text, single logical reading order). Options considered:
ReportLab (precise but a second template language), WeasyPrint (painful native deps on Windows),
and headless Chromium via Playwright.

## Decision
Author templates once in HTML/CSS. Render PDFs with Playwright-driven headless Chromium in a
sandboxed, network-disabled context with a render timeout and a bounded browser pool. Generate DOCX
separately with python-docx from the same structured resume model.

## Consequences
One template source for preview and export, so what the user sees is what they get. Output PDFs
contain real text, not images. Cost is a roughly 150 MB Chromium dependency and memory per render,
bounded by the pool; if Chromium is unavailable, DOCX export continues and PDF export honestly
reports unavailable. Untrusted content rendering is sandboxed per SECURITY.md.
