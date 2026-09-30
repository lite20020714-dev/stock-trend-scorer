"""Fetches data and scores a batch of stock codes, handling per-code failures gracefully."""

from __future__ import annotations

from dataclasses import dataclass

from .data import DataFetchError, PriceFetcher, get_fetcher
from .scoring import ScoreResult, TrendScorer


@dataclass(frozen=True)
class ScreeningError:
    code: str
    market: str
    message: str


@dataclass(frozen=True)
class ScreeningResult:
    market: str
    score: ScoreResult


def score_codes(
    codes: list[tuple[str, str]],
    scorer: TrendScorer,
    is_held: bool = False,
    period: str = "6mo",
) -> tuple[list[ScreeningResult], list[ScreeningError]]:
    """Fetch OHLCV data for each (code, market) pair and score it with `scorer`.

    A fetcher is created once per market and reused across codes (this
    matters for JQuantsFetcher, which caches its auth token across calls).
    A failure for one code (no data, network error, insufficient history)
    is collected as a ScreeningError instead of aborting the whole batch.
    """
    results: list[ScreeningResult] = []
    errors: list[ScreeningError] = []
    fetchers: dict[str, PriceFetcher] = {}

    for code, market in codes:
        try:
            if market not in fetchers:
                fetchers[market] = get_fetcher(market)
            df = fetchers[market].fetch_ohlcv(code, period=period)
            score = scorer.score(code, df, is_held=is_held)
            results.append(ScreeningResult(market=market, score=score))
        except (DataFetchError, ValueError) as exc:
            errors.append(ScreeningError(code=code, market=market, message=str(exc)))

    return results, errors
