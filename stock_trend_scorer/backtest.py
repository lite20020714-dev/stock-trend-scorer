"""Backtest: score stocks at past base dates and record how the price moved afterwards.

For each (code, base date) pair the scorer only sees data up to the base
date (so there is no look-ahead), and the following `horizon_months` of
prices are used to measure the outcome. The result is one flat record per
(code, base date), intended to be written to CSV and aggregated later,
e.g. "average 6-month return per score band".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable

import pandas as pd

from .data import DataFetchError, PriceFetcher, get_fetcher
from .scoring import TrendScorer

# Base dates default to monthly points from 30 to 6 months before the
# reference date (~2.5 years back), each evaluated over the next 6 months.
DEFAULT_START_MONTHS_AGO = 30
DEFAULT_END_MONTHS_AGO = 6
DEFAULT_STEP_MONTHS = 1
DEFAULT_HORIZON_MONTHS = 6

# History handed to the scorer at each base date. Matches `scan`'s default
# fetch window (1y) so backtest scores are comparable to live scan scores.
SCORING_LOOKBACK = pd.DateOffset(years=1)

# 2.5 years of base dates + 1 year of scoring lookback fits inside 5y.
DEFAULT_FETCH_PERIOD = "5y"

# The evaluation window counts as complete if the data runs to within this
# many days of its end (weekends/holidays mean the exact date may be missing).
EVAL_END_TOLERANCE = pd.Timedelta(days=7)

DEFAULT_SCORE_BANDS = [-1.0, -0.4, -0.2, 0.0, 0.2, 0.4, 1.0]


@dataclass(frozen=True)
class BacktestRecord:
    code: str
    market: str
    mode: str
    base_date: str  # trading day actually used (last trading day on/before the target date)
    eval_end_date: str  # last trading day of the evaluation window
    base_price: float
    score: float
    classification: str
    max_price: float
    min_price: float
    end_price: float
    max_return_pct: float
    min_return_pct: float
    end_return_pct: float
    week52_high_pct: float
    indicator_scores: dict[str, float] = field(default_factory=dict)

    def to_row(self) -> dict:
        row = asdict(self)
        indicators = row.pop("indicator_scores")
        row.update({f"ind_{name}": value for name, value in indicators.items()})
        return row


@dataclass(frozen=True)
class BacktestError:
    code: str
    market: str
    base_date: str | None  # None when the whole code failed (e.g. fetch error)
    message: str


def generate_base_dates(
    reference: pd.Timestamp,
    start_months_ago: int = DEFAULT_START_MONTHS_AGO,
    end_months_ago: int = DEFAULT_END_MONTHS_AGO,
    step_months: int = DEFAULT_STEP_MONTHS,
) -> list[pd.Timestamp]:
    """Target base dates from `start_months_ago` to `end_months_ago` before `reference`, oldest first."""
    if step_months <= 0:
        raise ValueError("step_months must be >= 1")
    if start_months_ago < end_months_ago:
        raise ValueError("start_months_ago must be >= end_months_ago")
    reference = pd.Timestamp(reference).normalize()
    return [
        reference - pd.DateOffset(months=months)
        for months in range(start_months_ago, end_months_ago - 1, -step_months)
    ]


def _return_pct(price: float, base_price: float) -> float:
    return round((price / base_price - 1) * 100, 2)


def evaluate_base_date(
    code: str,
    market: str,
    df: pd.DataFrame,
    target_date: pd.Timestamp,
    scorer: TrendScorer,
    horizon_months: int = DEFAULT_HORIZON_MONTHS,
    is_held: bool = False,
) -> BacktestRecord:
    """Score `df` as of `target_date` and measure the next `horizon_months` of price action.

    Raises ValueError if there is not enough history before the base date
    or the evaluation window is not fully covered by the data.
    """
    history = df.loc[:target_date]
    if history.empty:
        raise ValueError("no data on or before the base date")
    base_ts = history.index[-1]

    horizon_end = target_date + pd.DateOffset(months=horizon_months)
    if df.index[-1] < horizon_end - EVAL_END_TOLERANCE:
        raise ValueError("evaluation window extends past the available data")
    window = df.loc[(df.index > base_ts) & (df.index <= horizon_end)]
    if window.empty:
        raise ValueError("no data in the evaluation window")

    scored = scorer.score(code, history.loc[base_ts - SCORING_LOOKBACK :], is_held=is_held)
    base_price = round(scored.current_price, 4)
    max_price = round(float(window["high"].max()), 4)
    min_price = round(float(window["low"].min()), 4)
    end_price = round(float(window["close"].iloc[-1]), 4)

    return BacktestRecord(
        code=code,
        market=market,
        mode=scored.mode,
        base_date=base_ts.strftime("%Y-%m-%d"),
        eval_end_date=window.index[-1].strftime("%Y-%m-%d"),
        base_price=base_price,
        score=scored.total_score,
        classification=scored.classification,
        max_price=max_price,
        min_price=min_price,
        end_price=end_price,
        max_return_pct=_return_pct(max_price, base_price),
        min_return_pct=_return_pct(min_price, base_price),
        end_return_pct=_return_pct(end_price, base_price),
        week52_high_pct=scored.week52_high_pct,
        indicator_scores={i.name: round(i.score, 4) for i in scored.indicators},
    )


def run_backtest(
    codes: list[tuple[str, str]],
    scorer: TrendScorer,
    base_dates: list[pd.Timestamp],
    horizon_months: int = DEFAULT_HORIZON_MONTHS,
    is_held: bool = False,
    period: str = DEFAULT_FETCH_PERIOD,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[list[BacktestRecord], list[BacktestError]]:
    """Backtest every (code, market) pair at every base date.

    Each code's history is fetched once and reused for all base dates.
    Failures are collected per code (fetch errors) or per (code, base date)
    (e.g. not enough history yet) instead of aborting the run.
    """
    records: list[BacktestRecord] = []
    errors: list[BacktestError] = []
    fetchers: dict[str, PriceFetcher] = {}

    for index, (code, market) in enumerate(codes, start=1):
        if on_progress:
            on_progress(index, len(codes), code)
        try:
            if market not in fetchers:
                fetchers[market] = get_fetcher(market)
            df = fetchers[market].fetch_ohlcv(code, period=period)
        except (DataFetchError, ValueError) as exc:
            errors.append(BacktestError(code=code, market=market, base_date=None, message=str(exc)))
            continue

        for target_date in base_dates:
            try:
                records.append(
                    evaluate_base_date(code, market, df, target_date, scorer, horizon_months, is_held=is_held)
                )
            except ValueError as exc:
                errors.append(
                    BacktestError(
                        code=code, market=market, base_date=target_date.strftime("%Y-%m-%d"), message=str(exc)
                    )
                )

    return records, errors


def records_to_dataframe(records: list[BacktestRecord]) -> pd.DataFrame:
    return pd.DataFrame([r.to_row() for r in records])


def summarize_by_score_band(df: pd.DataFrame, bands: list[float] | None = None) -> pd.DataFrame:
    """Aggregate backtest rows per score band: sample count, mean/median returns, win rate.

    Bands are left-closed ([a, b)), except the last which also includes its
    upper edge so a score of exactly 1.0 is counted.
    """
    edges = sorted(bands or DEFAULT_SCORE_BANDS)
    labels = [
        f"[{lo:+.2f}, {hi:+.2f}{']' if i == len(edges) - 2 else ')'}"
        for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:]))
    ]
    # Nudge the top edge so the last band is closed on the right.
    cut_edges = edges[:-1] + [edges[-1] + 1e-9]
    band = pd.cut(df["score"], bins=cut_edges, labels=labels, right=False)

    grouped = df.groupby(band, observed=False)
    summary = pd.DataFrame(
        {
            "count": grouped.size(),
            "end_return_mean": grouped["end_return_pct"].mean(),
            "end_return_median": grouped["end_return_pct"].median(),
            "win_rate_pct": grouped["end_return_pct"].apply(lambda s: (s > 0).mean() * 100 if len(s) else float("nan")),
            "max_return_mean": grouped["max_return_pct"].mean(),
            "min_return_mean": grouped["min_return_pct"].mean(),
        }
    )
    summary.index.name = "score_band"
    return summary.round(2)
