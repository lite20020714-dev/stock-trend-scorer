"""Indicator weights and classification thresholds, externalized to JSON.

A config file only needs to specify the values it wants to override; any
key it omits falls back to the corresponding default below, so weights can
be tuned via backtesting without touching code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WEIGHTS: dict[str, float] = {
    "ma_cross": 1.0,
    "price_change": 1.0,
    "rsi": 1.0,
    "macd": 1.0,
    "volume": 1.0,
}

DEFAULT_THRESHOLDS: dict[str, float] = {
    "up": 0.3,
    "down": -0.3,
}


@dataclass(frozen=True)
class ScoringConfig:
    weights: dict[str, float]
    thresholds: dict[str, float]

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "scoring_weights.json"

def load_scoring_config(path: str | Path | None = None) -> ScoringConfig:
    weights = dict(DEFAULT_WEIGHTS)
    thresholds = dict(DEFAULT_THRESHOLDS)

    resolved_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if resolved_path.exists():
        data = json.loads(resolved_path.read_text(encoding="utf-8"))
        weights.update(data.get("weights", {}))
        thresholds.update(data.get("thresholds", {}))

    return ScoringConfig(weights=weights, thresholds=thresholds)
