import pandas as pd
import pytest

from stock_trend_scorer.scoring.scorer import (
    CLASSIFICATION_DOWN,
    CLASSIFICATION_NEUTRAL,
    CLASSIFICATION_UP,
    MODE_PERIODS,
    TrendScorer,
    _current_price,
    _week52_high_pct,
)
from stock_trend_scorer.scoring.weights import ScoringConfig


class TestTrendScorerInit:
    def test_discovery_mode_periods(self):
        scorer = TrendScorer(mode="discovery")
        assert scorer.periods == {"short": 5, "long": 25}

    def test_watch_mode_periods(self):
        scorer = TrendScorer(mode="watch")
        assert scorer.periods == {"short": 25, "long": 75}

    def test_unsupported_mode_raises(self):
        with pytest.raises(ValueError):
            TrendScorer(mode="bogus")


class TestTrendScorerScore:
    def test_insufficient_data_raises(self, trend_df_factory):
        df = trend_df_factory(n=10, flat_days=2, slope=1.0)
        scorer = TrendScorer(mode="discovery")
        with pytest.raises(ValueError):
            scorer.score("TEST", df)

    def test_returns_all_indicators(self, trend_df_factory):
        df = trend_df_factory(n=100, flat_days=60, slope=1.0, volume_slope=5000)
        scorer = TrendScorer(mode="discovery")
        result = scorer.score("TEST", df)
        names = {i.name for i in result.indicators}
        assert names == {"ma_cross", "price_change", "rsi", "macd", "volume"}

    def test_strong_uptrend_classified_as_up(self, trend_df_factory):
        df = trend_df_factory(n=100, flat_days=60, slope=2.0, volume_slope=5000)
        scorer = TrendScorer(mode="discovery")
        result = scorer.score("TEST", df)
        assert result.total_score > 0
        assert result.classification == CLASSIFICATION_UP

    def test_strong_downtrend_held_is_down_warning(self, trend_df_factory):
        df = trend_df_factory(n=100, flat_days=60, slope=-2.0, volume_slope=5000)
        scorer = TrendScorer(mode="watch")
        result = scorer.score("TEST", df, is_held=True)
        assert result.total_score < 0
        assert result.classification == CLASSIFICATION_DOWN

    def test_strong_downtrend_not_held_is_neutral_not_warning(self, trend_df_factory):
        df = trend_df_factory(n=100, flat_days=60, slope=-2.0, volume_slope=5000)
        scorer = TrendScorer(mode="watch")
        result = scorer.score("TEST", df, is_held=False)
        assert result.total_score < 0
        assert result.classification == CLASSIFICATION_NEUTRAL

    def test_weighted_average_isolates_single_indicator(self, trend_df_factory):
        df = trend_df_factory(n=100, flat_days=60, slope=2.0, volume_slope=5000)
        config = ScoringConfig(
            weights={"ma_cross": 0.0, "price_change": 0.0, "rsi": 1.0, "macd": 0.0, "volume": 0.0},
            thresholds={"up": 0.3, "down": -0.3},
        )
        scorer = TrendScorer(mode="discovery", config=config)
        result = scorer.score("TEST", df)
        assert result.total_score == result.indicator("rsi").score

    def test_zero_total_weight_gives_zero_score(self, trend_df_factory):
        df = trend_df_factory(n=100, flat_days=60, slope=2.0, volume_slope=5000)
        config = ScoringConfig(
            weights={"ma_cross": 0.0, "price_change": 0.0, "rsi": 0.0, "macd": 0.0, "volume": 0.0},
            thresholds={"up": 0.3, "down": -0.3},
        )
        scorer = TrendScorer(mode="discovery", config=config)
        result = scorer.score("TEST", df)
        assert result.total_score == 0.0
        assert result.classification == CLASSIFICATION_NEUTRAL

    def test_indicator_lookup_raises_for_unknown_name(self, trend_df_factory):
        df = trend_df_factory(n=100, flat_days=60, slope=1.0, volume_slope=5000)
        scorer = TrendScorer(mode="discovery")
        result = scorer.score("TEST", df)
        with pytest.raises(KeyError):
            result.indicator("nonexistent")

    def test_current_price_is_last_close(self, trend_df_factory):
        df = trend_df_factory(n=100, flat_days=60, slope=1.0, volume_slope=5000)
        scorer = TrendScorer(mode="discovery")
        result = scorer.score("TEST", df)
        assert result.current_price == pytest.approx(float(df["close"].iloc[-1]))


def _flat_df(n: int, close_values: list[float], high_values: list[float] | None = None) -> pd.DataFrame:
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    highs = high_values if high_values is not None else close_values
    return pd.DataFrame(
        {
            "open": close_values,
            "high": highs,
            "low": [min(c, h) - 1 for c, h in zip(close_values, highs)],
            "close": close_values,
            "volume": [1_000_000] * n,
        },
        index=dates,
    )


class TestPriceMetrics:
    def test_current_price_is_last_close(self):
        df = _flat_df(30, [100.0] * 29 + [110.0])
        assert _current_price(df) == 110.0

    def test_week52_high_pct_is_zero_at_the_high(self):
        df = _flat_df(30, [100.0] * 29 + [110.0])
        assert _week52_high_pct(df) == 0.0

    def test_week52_high_pct_negative_below_the_high(self):
        df = _flat_df(30, [100.0] * 29 + [90.0])
        pct = _week52_high_pct(df)
        assert pct == pytest.approx((90.0 / 100.0 - 1) * 100, rel=1e-6)
        assert pct < 0

    def test_week52_high_uses_only_trailing_252_rows(self):
        n = 300
        closes = [100.0] * n
        highs = [100.0] * n
        highs[0] = 500.0  # spike far outside the trailing ~52-week window
        df = _flat_df(n, closes, highs)
        assert _week52_high_pct(df) == 0.0

    def test_week52_high_pct_included_in_score_result(self, trend_df_factory):
        df = trend_df_factory(n=100, flat_days=60, slope=-2.0, volume_slope=5000)
        scorer = TrendScorer(mode="discovery")
        result = scorer.score("TEST", df)
        assert result.week52_high_pct < 0
