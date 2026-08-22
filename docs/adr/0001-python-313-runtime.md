# ADR-0001: Python 3.13 as the backend runtime

Status: Accepted (2026-08-22)

## Context
The machine exposes Python 3.10.11 (on PATH as "python"), 3.11.9, 3.13.5 and 3.14.3 (default for
the py launcher). FastAPI and Pydantic v2 need 3.11+ for the typing features we rely on. Python
3.14 is new enough that some parsing and ONNX dependencies may lack wheels.

## Decision
Target Python 3.13.5, pinned via the py launcher (py -3.13) and a project virtualenv.

## Consequences
Full wheel coverage for pdfplumber, python-docx, onnxruntime and Playwright; modern typing and
asyncio. CI pins the same version. Revisit when 3.14 wheel coverage is complete.
