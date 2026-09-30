"""Common interface implemented by every price data fetcher."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

#: Columns present in every DataFrame returned by fetch_ohlcv, in this order.
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class PriceFetcher(ABC):
    """Fetches historical OHLCV price data for a single stock code."""

    @abstractmethod
    def fetch_ohlcv(self, code: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """Return OHLCV data for ``code``.

        The result is indexed by date (ascending) with columns
        ``open``, ``high``, ``low``, ``close``, ``volume``.

        Raises:
            SymbolNotFoundError: no data was returned for ``code``.
            DataFetchError: the request failed or returned malformed data.
        """
        raise NotImplementedError
