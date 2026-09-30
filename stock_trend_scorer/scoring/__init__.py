"""Trend scoring: technical indicators combined into a weighted -1..+1 score."""

from .indicators import IndicatorScore
from .scorer import (
    CLASSIFICATION_DOWN,
    CLASSIFICATION_NEUTRAL,
    CLASSIFICATION_UP,
    MODE_PERIODS,
    ScoreResult,
    TrendScorer,
)
from .weights import ScoringConfig, load_scoring_config

__all__ = [
    "IndicatorScore",
    "ScoreResult",
    "TrendScorer",
    "MODE_PERIODS",
    "CLASSIFICATION_UP",
    "CLASSIFICATION_DOWN",
    "CLASSIFICATION_NEUTRAL",
    "ScoringConfig",
    "load_scoring_config",
]
