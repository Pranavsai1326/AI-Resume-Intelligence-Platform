"""JSON-in-prompt structured output with one bounded repair attempt (AI_ARCHITECTURE.md section 4).

The prompt asks the model for JSON directly rather than relying on a provider-specific tool-use
feature - this keeps ``LLMProvider`` a plain text-completion interface any provider can implement,
at the cost of needing to parse and validate what comes back. Failure handling: strict JSON parse,
then Pydantic schema validation; on either failure, one repair attempt re-sends the broken output
with the parser error, then gives up cleanly. Never raises past this module - a schema mismatch or
a second failed parse is reported as ``None``, the same "unavailable" signal as no provider being
configured at all, so callers do not need two different failure branches.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from app.ai.prompts import PromptSpec
from app.ai.providers import LLMProvider
from app.logging import get_logger

logger = get_logger(__name__)

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(text: str) -> str:
    stripped = _CODE_FENCE_RE.sub("", text.strip()).strip()
    # A model occasionally wraps the object in a sentence despite instructions; take the
    # outermost {...} span rather than failing outright.
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def _try_parse[T: BaseModel](text: str, schema: type[T]) -> tuple[T | None, str | None]:
    candidate = _extract_json(text)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {exc}"
    try:
        return schema.model_validate(data), None
    except ValidationError as exc:
        return None, f"Did not match the required schema: {exc}"


async def complete_structured[T: BaseModel](
    provider: LLMProvider, *, spec: PromptSpec, user: str, schema: type[T]
) -> T | None:
    """Run ``spec`` against ``provider`` and parse the result as ``schema``.

    Returns ``None`` on provider unavailability, an empty completion, or a schema mismatch that
    survives one repair attempt - the caller turns that into an honest "unavailable" response,
    never a fabricated or partially-filled result.
    """
    truncated = user[: spec.max_input_chars]
    response = await provider.complete(
        system=spec.system,
        user=truncated,
        max_tokens=spec.max_output_tokens,
        temperature=spec.temperature,
    )
    if response is None or not response.text.strip():
        return None

    parsed, error = _try_parse(response.text, schema)
    if parsed is not None:
        return parsed

    repair_user = (
        f"{truncated}\n\n---\nYour previous response could not be used: {error}\nPrevious "
        f"response:\n{response.text}\n\nReturn ONLY the corrected JSON object, nothing else."
    )
    repair_response = await provider.complete(
        system=spec.system,
        user=repair_user,
        max_tokens=spec.max_output_tokens,
        temperature=spec.temperature,
    )
    if repair_response is None or not repair_response.text.strip():
        return None

    parsed, error = _try_parse(repair_response.text, schema)
    if parsed is None:
        logger.warning("ai.structured_output_failed", prompt_id=spec.id)
    return parsed
