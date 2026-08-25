"""Prompt registry (AI_ARCHITECTURE.md section 3).

Every prompt sent to the LLM is a versioned, data-driven record here - never an inline string
scattered through business logic. Changing wording bumps the version so evaluations stay
comparable. Nothing here calls a provider; this module is pure data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptSpec:
    id: str
    version: str
    system: str
    #: Input is truncated at this many characters before being sent, with the truncation
    #: disclosed to the caller rather than silently applied (AI_ARCHITECTURE.md section 7).
    max_input_chars: int
    max_output_tokens: int
    temperature: float


_NO_INVENTION = (
    "You MUST NOT invent any fact not present in the original text: no new numbers, "
    "percentages, team sizes, employers, technologies, dates, or outcomes. If the original "
    "has no metric, do not add one. Rewrite only what is already stated, in better words."
)

REWRITE_BULLET = PromptSpec(
    id="rewrite_bullet",
    version="1.0.0",
    system=(
        "You improve a single resume bullet point. Rewrite it to open with a strong, direct "
        f"action verb and read professionally and concisely. {_NO_INVENTION} Return only the "
        "rewritten bullet text - no quotes, no preamble, no explanation, no markdown."
    ),
    max_input_chars=400,
    max_output_tokens=120,
    temperature=0.3,
)

REWRITE_SUMMARY = PromptSpec(
    id="rewrite_summary",
    version="1.0.0",
    system=(
        "You improve a resume's professional summary. Rewrite it to be concise (2-3 sentences) "
        f"and professionally toned. {_NO_INVENTION} Return only the rewritten summary text - no "
        "quotes, no preamble, no explanation, no markdown."
    ),
    max_input_chars=800,
    max_output_tokens=200,
    temperature=0.3,
)

TAILOR_BULLET = PromptSpec(
    id="tailor_bullet",
    version="1.0.0",
    system=(
        "You are helping tailor a resume bullet to better match a specific job description, "
        "by re-emphasising skills and outcomes already present in the bullet - never by adding "
        f"new ones. {_NO_INVENTION} You will be given the bullet and a short list of the job's "
        "relevant keywords already present in the bullet; lead with them where natural. Return "
        "only the rewritten bullet text - no quotes, no preamble, no explanation, no markdown."
    ),
    max_input_chars=500,
    max_output_tokens=120,
    temperature=0.3,
)
