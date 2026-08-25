"""Small shared helpers for building point-based component scores."""

from __future__ import annotations


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))
