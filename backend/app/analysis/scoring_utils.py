"""Small shared helpers for building point-based component scores."""

from __future__ import annotations

from app.analysis.models import ComponentScore


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def apply_degrade_and_renormalize(
    components: dict[str, ComponentScore],
) -> tuple[dict[str, ComponentScore], float, list[str]]:
    """Exclude unavailable components from the overall and renormalise the rest.

    Shared by every scoring engine (resume health, job match): each returns
    ``{key: ComponentScore}`` built with each component's *configured* weight, and this function
    is what turns that into the actual overall plus the weights a response should report.
    ``ComponentScore.weight`` is documented as "the weight actually used" - so an available
    component's weight is rewritten here to its renormalised share; an unavailable one keeps its
    configured weight unchanged (nothing was "used", but the value stays meaningful as "what this
    would have counted for").
    """
    degraded = [key for key, component in components.items() if not component.available]
    available_weight_total = sum(c.weight for c in components.values() if c.available)

    result: dict[str, ComponentScore] = {}
    overall = 0.0
    for key, component in components.items():
        if not component.available or available_weight_total <= 0:
            result[key] = component
            continue
        normalized_weight = component.weight / available_weight_total
        result[key] = component.model_copy(update={"weight": normalized_weight})
        overall += component.score * normalized_weight

    return result, round(overall, 1), degraded
