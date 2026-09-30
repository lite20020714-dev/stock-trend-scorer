"""Individual technical indicator scores, each normalized to the range [-1, 1].

+1 is the strongest possible uptrend signal, -1 the strongest downtrend
signal, and 0 is neutral.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pandas_ta as ta


@dataclass(frozen=True)
class IndicatorScore:
    name: str
    score: float
    details: dict = field(default_factory=dict)


def _clip(value: float) -> float:
    return float(np.clip(value, -1.0, 1.0))


def _detect_cross(diff: pd.Series, lookback: int) -> tuple[bool, bool]:
    """Scan the last `lookback` transitions of a (fast - slow) series for a crossover."""
    recent = diff.tail(lookback + 1).to_numpy()
    golden = any(recent[i - 1] <= 0 < recent[i] for i in range(1, len(recent)))
    dead = any(recent[i - 1] >= 0 > recent[i] for i in range(1, len(recent)))
    return golden, dead


def score_ma_cross(
    df: pd.DataFrame, short: int, long: int, cross_lookback: int = 3, scale: float = 0.05
) -> IndicatorScore:
    """Golden-cross / dead-cross of the short vs. long SMA."""
    close = df["close"]
    short_ma = close.rolling(short).mean()
    long_ma = close.rolling(long).mean()
    if long_ma.dropna().empty:
        raise ValueError(f"Not enough data to compute the {long}-day moving average")

    diff_ratio = (short_ma.iloc[-1] - long_ma.iloc[-1]) / long_ma.iloc[-1]
    score = _clip(diff_ratio / scale)

    diff_series = (short_ma - long_ma).dropna()
    golden_cross, dead_cross = _detect_cross(diff_series, cross_lookback)
    if golden_cross:
        score = _clip(max(score, 0.7))
    elif dead_cross:
        score = _clip(min(score, -0.7))

    return IndicatorScore(
        name="ma_cross",
        score=score,
        details={
            "short_ma": float(short_ma.iloc[-1]),
            "long_ma": float(long_ma.iloc[-1]),
            "golden_cross": golden_cross,
            "dead_cross": dead_cross,
        },
    )


def score_price_change(df: pd.DataFrame, n: int, scale: float = 0.1) -> IndicatorScore:
    """Rate of change of the close price over the last N days."""
    close = df["close"]
    if len(close) <= n:
        raise ValueError(f"Not enough data to compute the {n}-day price change")

    change_rate = (close.iloc[-1] - close.iloc[-1 - n]) / close.iloc[-1 - n]
    score = float(np.tanh(change_rate / scale))
    return IndicatorScore(name="price_change", score=score, details={"change_rate": float(change_rate), "n": n})


def score_rsi(df: pd.DataFrame, period: int = 14) -> IndicatorScore:
    """RSI mapped as a momentum signal (this tool screens for trend strength,
    not mean-reversion, so a high RSI counts as bullish rather than 'overbought')."""
    rsi = ta.rsi(df["close"], length=period)
    if rsi is None or rsi.dropna().empty:
        raise ValueError(f"Not enough data to compute RSI({period})")

    latest_rsi = float(rsi.iloc[-1])
    score = _clip((latest_rsi - 50) / 50)
    return IndicatorScore(name="rsi", score=score, details={"rsi": latest_rsi})


def score_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    cross_lookback: int = 3,
    scale: float = 0.02,
) -> IndicatorScore:
    """MACD line vs. signal line, normalized by price so it is scale-free across stocks."""
    close = df["close"]
    macd_df = ta.macd(close, fast=fast, slow=slow, signal=signal)
    macd_col, signal_col = f"MACD_{fast}_{slow}_{signal}", f"MACDs_{fast}_{slow}_{signal}"
    if macd_df is None or macd_col not in macd_df:
        raise ValueError("Not enough data to compute MACD")

    diff = (macd_df[macd_col] - macd_df[signal_col]).dropna()
    if diff.empty:
        raise ValueError("Not enough data to compute MACD")

    score = _clip(float(diff.iloc[-1] / close.iloc[-1]) / scale)

    golden_cross, dead_cross = _detect_cross(diff, cross_lookback)
    if golden_cross:
        score = _clip(max(score, 0.7))
    elif dead_cross:
        score = _clip(min(score, -0.7))

    return IndicatorScore(
        name="macd",
        score=score,
        details={
            "macd": float(macd_df[macd_col].iloc[-1]),
            "signal": float(macd_df[signal_col].iloc[-1]),
            "golden_cross": golden_cross,
            "dead_cross": dead_cross,
        },
    )


def score_volume(df: pd.DataFrame, short: int, long: int, scale: float = 0.5) -> IndicatorScore:
    """Volume increase/decrease, signed by the concurrent price direction.

    Rising volume confirms whatever trend the price is already showing;
    falling volume carries no directional signal (score decays toward 0).
    """
    volume, close = df["volume"], df["close"]
    if len(volume) < long or len(close) <= short:
        raise ValueError(f"Not enough data to compute the {long}-day volume average")

    short_avg = float(volume.tail(short).mean())
    long_avg = float(volume.tail(long).mean())
    volume_ratio = short_avg / long_avg if long_avg else 1.0

    price_change = (close.iloc[-1] - close.iloc[-1 - short]) / close.iloc[-1 - short]
    direction = float(np.sign(price_change))

    strength = _clip(max(volume_ratio - 1.0, 0.0) / scale)
    score = _clip(direction * strength)

    return IndicatorScore(
        name="volume",
        score=score,
        details={"volume_ratio": volume_ratio, "price_direction": direction},
    )
