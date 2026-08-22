# ADR-0004: pdfplumber plus pypdf for PDF extraction

Status: Accepted (2026-08-22)

## Context
ATS analysis needs more than raw text: it needs word-level geometry to detect multi-column layouts,
tables, text boxes, images and header/footer content. PyMuPDF provides excellent layout data but is
AGPL-3.0 without a commercial licence, which is a poor fit for a product intended for deployment.

## Decision
Use pdfplumber (MIT, over pdfminer.six) for text with word bounding boxes, plus pypdf (BSD) for
document-level metadata, page counts and structural checks. Keep extraction behind an interface so
a licensed high-performance parser can be swapped in later.

## Consequences
Permissive licensing throughout. Column and table detection is built on real coordinates rather than
guesswork. pdfplumber is slower than PyMuPDF on large files, mitigated by page limits, per-parse
timeouts and async offloading. The xpdf pdftotext binary present on this machine is not a dependency.
