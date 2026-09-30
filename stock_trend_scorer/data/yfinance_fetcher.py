"""OHLCV fetcher backed by yfinance.

Used directly for US tickers (e.g. "AAPL"), and as a fallback / default
source for JP stocks by appending the Tokyo Stock Exchange suffix
(e.g. "7203" -> "7203.T"), avoiding the need for J-Quants credentials.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from .base import OHLCV_COLUMNS, PriceFetcher
from .exceptions import DataFetchError, SymbolNotFoundError

_JP_SUFFIX = ".T"

_YFINANCE_COLUMN_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
}


def normalize_jp_code(code: str) -> str:
    """Convert a raw JP stock code (e.g. "7203") to Yahoo Finance format ("7203.T")."""
    normalized = code.strip().upper()
    if normalized.endswith(_JP_SUFFIX):
        return normalized
    return f"{normalized}{_JP_SUFFIX}"


class YFinanceFetcher(PriceFetcher):
    """Fetches OHLCV data via yfinance for either the US or JP market."""

    def __init__(self, market: str = "US"):
        market = market.upper()
        if market not in ("US", "JP"):
            raise ValueError(f"Unsupported market: {market!r}")
        self.market = market

    def _resolve_symbol(self, code: str) -> str:
        if self.market == "JP":
            return normalize_jp_code(code)
        return code.strip().upper()

    def fetch_ohlcv(self, code: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        symbol = self._resolve_symbol(code)
        try:
            df = yf.download(
                symbol,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
            )
        except Exception as exc:  # yfinance raises a variety of exception types
            raise DataFetchError(f"Failed to fetch data for {symbol}: {exc}") from exc

        if df is None or df.empty:
            raise SymbolNotFoundError(f"No data returned for {symbol}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.rename(columns=_YFINANCE_COLUMN_MAP)
        missing = set(_YFINANCE_COLUMN_MAP.values()) - set(df.columns)
        if missing:
            raise DataFetchError(f"Missing columns {sorted(missing)} for {symbol}")

        df = df[OHLCV_COLUMNS].sort_index()
        # yfinance sometimes returns the most recent bar with NaN fields
        # (e.g. an in-progress/not-yet-finalized session); drop anything
        # incomplete rather than let it poison every downstream calculation.
        df = df.dropna()
        if df.empty:
            raise SymbolNotFoundError(f"No usable (non-NaN) data returned for {symbol}")
        df.index.name = "date"
        df.columns.name = None
        return df
