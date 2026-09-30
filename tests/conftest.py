import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [105.0, 106.0, 107.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [104.0, 105.0, 106.0],
            "Volume": [1000, 1100, 1200],
        },
        index=dates,
    )


def make_recent_trend_df(
    n: int = 100,
    flat_days: int = 60,
    slope: float = 1.0,
    start_price: float = 100.0,
    volume_start: float = 1_000_000,
    volume_slope: float = 0.0,
    noise: float = 0.0,
    seed: int = 0,
) -> pd.DataFrame:
    """OHLCV data that is flat for `flat_days`, then trends linearly at `slope`/day.

    Mimics a stock that has just entered a new trend, which is what the
    discovery/watch scoring modes are meant to detect. `slope`/`volume_slope`
    can be negative to build a downtrend.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = np.where(t < flat_days, start_price, start_price + slope * (t - flat_days + 1)).astype(float)
    if noise:
        close = close + rng.normal(0, noise, n)
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + 0.5
    low = np.minimum(open_, close) - 0.5
    volume = volume_start + np.where(t < flat_days, 0, volume_slope * (t - flat_days + 1))
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=dates)


@pytest.fixture
def trend_df_factory():
    return make_recent_trend_df
