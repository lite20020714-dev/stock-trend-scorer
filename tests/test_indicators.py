import pandas as pd
import pytest

from stock_trend_scorer.scoring import indicators as ind


class TestDetectCross:
    def test_golden_cross_detected(self):
        diff = pd.Series([-2.0, -1.0, 0.5, 1.5])
        golden, dead = ind._detect_cross(diff, lookback=3)
        assert golden is True
        assert dead is False

    def test_dead_cross_detected(self):
        diff = pd.Series([2.0, 1.0, -0.5, -1.5])
        golden, dead = ind._detect_cross(diff, lookback=3)
        assert golden is False
        assert dead is True

    def test_no_cross_when_no_sign_change(self):
        diff = pd.Series([1.0, 1.2, 1.4, 1.6])
        golden, dead = ind._detect_cross(diff, lookback=3)
        assert golden is False
        assert dead is False

    def test_cross_outside_lookback_window_is_ignored(self):
        diff = pd.Series([-1.0, 1.0, 1.1, 1.2, 1.3])
        golden, dead = ind._detect_cross(diff, lookback=2)
        assert golden is False
        assert dead is False


class TestScoreMaCross:
    def test_uptrend_is_positive(self, trend_df_factory):
        df = trend_df_factory(slope=1.0)
        result = ind.score_ma_cross(df, short=5, long=25)
        assert result.name == "ma_cross"
        assert result.score > 0

    def test_downtrend_is_negative(self, trend_df_factory):
        df = trend_df_factory(slope=-1.0)
        result = ind.score_ma_cross(df, short=5, long=25)
        assert result.score < 0

    def test_score_bounded(self, trend_df_factory):
        df = trend_df_factory(slope=50.0)
        result = ind.score_ma_cross(df, short=5, long=25)
        assert -1.0 <= result.score <= 1.0

    def test_insufficient_data_raises(self, trend_df_factory):
        df = trend_df_factory(n=10, flat_days=5, slope=1.0)
        with pytest.raises(ValueError):
            ind.score_ma_cross(df, short=5, long=25)


class TestScorePriceChange:
    def test_uptrend_is_positive(self, trend_df_factory):
        df = trend_df_factory(slope=1.0)
        result = ind.score_price_change(df, n=5)
        assert result.score > 0

    def test_downtrend_is_negative(self, trend_df_factory):
        df = trend_df_factory(slope=-1.0)
        result = ind.score_price_change(df, n=5)
        assert result.score < 0

    def test_score_bounded_for_extreme_move(self, trend_df_factory):
        df = trend_df_factory(slope=1000.0)
        result = ind.score_price_change(df, n=5)
        assert -1.0 <= result.score <= 1.0

    def test_insufficient_data_raises(self, trend_df_factory):
        df = trend_df_factory(n=3, flat_days=1, slope=1.0)
        with pytest.raises(ValueError):
            ind.score_price_change(df, n=5)


class TestScoreRsi:
    def test_uptrend_is_positive(self, trend_df_factory):
        df = trend_df_factory(slope=1.0)
        result = ind.score_rsi(df)
        assert result.score > 0
        assert result.details["rsi"] > 50

    def test_downtrend_is_negative(self, trend_df_factory):
        df = trend_df_factory(slope=-1.0)
        result = ind.score_rsi(df)
        assert result.score < 0
        assert result.details["rsi"] < 50

    def test_score_bounded(self, trend_df_factory):
        df = trend_df_factory(slope=1.0)
        result = ind.score_rsi(df)
        assert -1.0 <= result.score <= 1.0

    def test_insufficient_data_raises(self, trend_df_factory):
        df = trend_df_factory(n=5, flat_days=1, slope=1.0)
        with pytest.raises(ValueError):
            ind.score_rsi(df, period=14)


class TestScoreMacd:
    def test_uptrend_is_positive(self, trend_df_factory):
        df = trend_df_factory(slope=1.0)
        result = ind.score_macd(df)
        assert result.score > 0

    def test_downtrend_is_negative(self, trend_df_factory):
        df = trend_df_factory(slope=-1.0)
        result = ind.score_macd(df)
        assert result.score < 0

    def test_score_bounded(self, trend_df_factory):
        df = trend_df_factory(slope=1000.0)
        result = ind.score_macd(df)
        assert -1.0 <= result.score <= 1.0

    def test_insufficient_data_raises(self, trend_df_factory):
        df = trend_df_factory(n=10, flat_days=2, slope=1.0)
        with pytest.raises(ValueError):
            ind.score_macd(df)


class TestScoreVolume:
    def test_rising_volume_confirms_uptrend(self, trend_df_factory):
        df = trend_df_factory(slope=1.0, volume_slope=5000)
        result = ind.score_volume(df, short=5, long=25)
        assert result.score > 0

    def test_rising_volume_confirms_downtrend(self, trend_df_factory):
        df = trend_df_factory(slope=-1.0, volume_slope=5000)
        result = ind.score_volume(df, short=5, long=25)
        assert result.score < 0

    def test_falling_volume_gives_no_signal(self, trend_df_factory):
        df = trend_df_factory(slope=1.0, volume_slope=-3000)
        result = ind.score_volume(df, short=5, long=25)
        assert result.score == 0.0

    def test_score_bounded(self, trend_df_factory):
        df = trend_df_factory(slope=1.0, volume_slope=1_000_000)
        result = ind.score_volume(df, short=5, long=25)
        assert -1.0 <= result.score <= 1.0

    def test_insufficient_data_raises(self, trend_df_factory):
        df = trend_df_factory(n=10, flat_days=2, slope=1.0)
        with pytest.raises(ValueError):
            ind.score_volume(df, short=5, long=25)
