"""Combines indicator scores into a single weighted trend score and classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import indicators as ind
from .weights import ScoringConfig, load_scoring_config

# 新規発掘用: 短期5日/長期25日, 保有監視用: 短期25日/長期75日
MODE_PERIODS: dict[str, dict[str, int]] = {
    "discovery": {"short": 5, "long": 25},
    "watch": {"short": 25, "long": 75},
}

CLASSIFICATION_UP = "上昇トレンド候補"
CLASSIFICATION_DOWN = "下落トレンド警告"
CLASSIFICATION_NEUTRAL = "様子見"

# Trailing window used for the "52-week" high; a true 52-week figure requires
# the caller to have fetched at least this much history (period="1y"+).
# With a shorter fetch window this degrades gracefully to a "period high".
TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class ScoreResult:
    code: str
    mode: str
    total_score: float
    classification: str
    indicators: list[ind.IndicatorScore]
    current_price: float = 0.0
    week52_high_pct: float = 0.0

    def indicator(self, name: str) -> ind.IndicatorScore:
        for item in self.indicators:
            if item.name == name:
                return item
        raise KeyError(name)


def _current_price(df: pd.DataFrame) -> float:
    return float(df["close"].iloc[-1])


def _week52_high_pct(df: pd.DataFrame) -> float:
    """Deviation of the current close from the trailing ~52-week high, in percent.

    Negative means the current price is below the 52-week high (the usual
    case); 0 means the current price *is* the 52-week high.
    """
    window = df.tail(TRADING_DAYS_PER_YEAR)
    week52_high = float(window["high"].max())
    current_price = _current_price(df)
    return round((current_price / week52_high - 1) * 100, 2)


class TrendScorer:
    """Scores a single stock's OHLCV history for trend strength/direction."""

    def __init__(
        self,
        mode: str,
        config: ScoringConfig | None = None,
        config_path: str | Path | None = None,
    ):
        if mode not in MODE_PERIODS:
            raise ValueError(f"Unsupported mode: {mode!r}. Use one of {list(MODE_PERIODS)}")
        self.mode = mode
        self.periods = MODE_PERIODS[mode]
        self.config = config or load_scoring_config(config_path)

    def score(self, code: str, df: pd.DataFrame, is_held: bool = False) -> ScoreResult:
        short, long = self.periods["short"], self.periods["long"]
        required = long + 1
        if len(df) < required:
            raise ValueError(f"Not enough data for {code}: need at least {required} rows, got {len(df)}")

        indicator_scores = [
            ind.score_ma_cross(df, short=short, long=long),
            ind.score_price_change(df, n=short),
            ind.score_rsi(df),
            ind.score_macd(df),
            ind.score_volume(df, short=short, long=long),
        ]

        total_score = self._weighted_average(indicator_scores)
        classification = self._classify(total_score, is_held)

        return ScoreResult(
            code=code,
            mode=self.mode,
            total_score=total_score,
            classification=classification,
            indicators=indicator_scores,
            current_price=_current_price(df),
            week52_high_pct=_week52_high_pct(df),
        )

    def _weighted_average(self, scores: list[ind.IndicatorScore]) -> float:
        weights = self.config.weights
        total_weight = sum(weights.get(s.name, 1.0) for s in scores)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(s.score * weights.get(s.name, 1.0) for s in scores)
        return round(weighted_sum / total_weight, 4)

    def _classify(self, total_score: float, is_held: bool) -> str:
        thresholds = self.config.thresholds
        if total_score >= thresholds["up"]:
            return CLASSIFICATION_UP
        if is_held and total_score <= thresholds["down"]:
            return CLASSIFICATION_DOWN
        return CLASSIFICATION_NEUTRAL
