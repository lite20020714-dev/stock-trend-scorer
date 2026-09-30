"""Selects the appropriate PriceFetcher for a given market."""

from __future__ import annotations

from ..config import load_settings
from .base import PriceFetcher
from .jquants_fetcher import JQuantsFetcher
from .yfinance_fetcher import YFinanceFetcher


def get_fetcher(market: str) -> PriceFetcher:
    """Return a PriceFetcher for ``market`` ("US" or "JP").

    US always uses yfinance. JP uses yfinance by default; set the
    JP_DATA_SOURCE=jquants environment variable (with J-Quants credentials)
    to use the J-Quants API instead.
    """
    market = market.upper()
    if market == "US":
        return YFinanceFetcher(market="US")
    if market == "JP":
        settings = load_settings()
        if settings.jp_data_source == "jquants":
            return JQuantsFetcher(
                mail_address=settings.jquants_mail_address,
                password=settings.jquants_password,
                refresh_token=settings.jquants_refresh_token,
            )
        return YFinanceFetcher(market="JP")
    raise ValueError(f"Unsupported market: {market!r}")
