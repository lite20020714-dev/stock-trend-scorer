from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from stock_trend_scorer import backtest as bt
from stock_trend_scorer.data.exceptions import SymbolNotFoundError
from stock_trend_scorer.scoring import CLASSIFICATION_NEUTRAL, CLASSIFICATION_UP, TrendScorer


def make_daily_df(start: str, end: str, close_fn=None) -> pd.DataFrame:
    """Business-day OHLCV where close = close_fn(i); high/low are close ±1."""
    dates = pd.bdate_range(start, end)
    i = np.arange(len(dates))
    close = close_fn(i) if close_fn else 100.0 + i * 0.1
    return pd.DataFrame(
        {"open": close, "high": close + 1.0, "low": close - 1.0, "close": close, "volume": 1_000_000.0},
        index=dates,
    )


class TestGenerateBaseDates:
    def test_default_range_is_monthly_from_30_to_6_months_ago(self):
        dates = bt.generate_base_dates(pd.Timestamp("2026-09-24"))
        assert len(dates) == 25
        assert dates[0] == pd.Timestamp("2024-03-24")
        assert dates[-1] == pd.Timestamp("2026-03-24")
        assert dates == sorted(dates)

    def test_step_months(self):
        dates = bt.generate_base_dates(pd.Timestamp("2026-09-24"), start_months_ago=12, end_months_ago=6, step_months=3)
        assert dates == [pd.Timestamp("2025-09-24"), pd.Timestamp("2025-12-24"), pd.Timestamp("2026-03-24")]

    def test_invalid_range_raises(self):
        with pytest.raises(ValueError):
            bt.generate_base_dates(pd.Timestamp("2026-09-24"), start_months_ago=3, end_months_ago=6)
        with pytest.raises(ValueError):
            bt.generate_base_dates(pd.Timestamp("2026-09-24"), step_months=0)


class TestEvaluateBaseDate:
    def test_records_base_price_and_forward_extremes(self):
        df = make_daily_df("2023-01-02", "2025-12-31")
        target = pd.Timestamp("2024-06-15")  # a Saturday -> base is Friday 2024-06-14

        record = bt.evaluate_base_date("AAPL", "US", df, target, TrendScorer(mode="discovery"), horizon_months=6)

        base_ts = pd.Timestamp("2024-06-14")
        window = df.loc[(df.index > base_ts) & (df.index <= pd.Timestamp("2024-12-15"))]
        base_price = df.loc[base_ts, "close"]

        assert record.base_date == "2024-06-14"
        assert record.eval_end_date == "2024-12-13"
        assert record.base_price == pytest.approx(base_price)
        assert record.max_price == pytest.approx(window["high"].max())
        assert record.min_price == pytest.approx(window["low"].min())
        assert record.end_price == pytest.approx(window["close"].iloc[-1])
        assert record.end_return_pct == pytest.approx(round((record.end_price / base_price - 1) * 100, 2))
        assert record.max_return_pct > record.end_return_pct > 0
        assert set(record.indicator_scores) == {"ma_cross", "price_change", "rsi", "macd", "volume"}

    def test_scorer_does_not_see_future_data(self):
        df = make_daily_df("2023-01-02", "2025-12-31")
        target = pd.Timestamp("2024-06-14")
        scorer = MagicMock(spec=TrendScorer)
        scorer.score.return_value = TrendScorer(mode="discovery").score("X", df.loc[:target])

        bt.evaluate_base_date("X", "US", df, target, scorer)

        seen = scorer.score.call_args.args[1]
        assert seen.index[-1] == target
        # Only ~1 year of lookback is handed to the scorer, same as `scan`.
        assert seen.index[0] >= target - pd.DateOffset(years=1)

    def test_uptrend_then_crash_is_up_candidate_with_negative_return(self):
        # Rising into the base date, then falling sharply afterwards.
        dates = pd.bdate_range("2023-01-02", "2025-06-30")
        base_idx = dates.get_indexer([pd.Timestamp("2024-06-14")])[0]

        def close_fn(i):
            return np.where(i <= base_idx, 100 + np.maximum(i - (base_idx - 30), 0) * 2.0, 160 - (i - base_idx) * 0.3)

        df = make_daily_df("2023-01-02", "2025-06-30", close_fn)
        record = bt.evaluate_base_date("X", "US", df, pd.Timestamp("2024-06-14"), TrendScorer(mode="discovery"))

        assert record.classification == CLASSIFICATION_UP
        assert record.end_return_pct < 0
        assert record.min_return_pct < record.end_return_pct

    def test_not_enough_history_raises(self):
        df = make_daily_df("2024-06-01", "2025-06-30")
        with pytest.raises(ValueError):
            bt.evaluate_base_date("X", "US", df, pd.Timestamp("2024-06-14"), TrendScorer(mode="discovery"))

    def test_base_date_before_data_starts_raises(self):
        df = make_daily_df("2024-06-01", "2025-06-30")
        with pytest.raises(ValueError, match="no data on or before"):
            bt.evaluate_base_date("X", "US", df, pd.Timestamp("2024-01-15"), TrendScorer(mode="discovery"))

    def test_incomplete_evaluation_window_raises(self):
        df = make_daily_df("2023-01-02", "2024-09-30")
        with pytest.raises(ValueError, match="evaluation window"):
            bt.evaluate_base_date("X", "US", df, pd.Timestamp("2024-06-14"), TrendScorer(mode="discovery"))


class TestRunBacktest:
    def test_fetches_once_per_code_and_evaluates_every_base_date(self, monkeypatch):
        fetcher = MagicMock()
        fetcher.fetch_ohlcv.return_value = make_daily_df("2023-01-02", "2025-12-31")
        monkeypatch.setattr("stock_trend_scorer.backtest.get_fetcher", lambda market: fetcher)

        base_dates = [pd.Timestamp("2024-03-15"), pd.Timestamp("2024-04-15"), pd.Timestamp("2024-05-15")]
        records, errors = bt.run_backtest(
            [("AAPL", "US"), ("MSFT", "US")], scorer=TrendScorer(mode="discovery"), base_dates=base_dates
        )

        assert errors == []
        assert len(records) == 6
        assert fetcher.fetch_ohlcv.call_count == 2
        fetcher.fetch_ohlcv.assert_any_call("AAPL", period=bt.DEFAULT_FETCH_PERIOD)

    def test_fetch_failure_and_per_date_failures_are_collected(self, monkeypatch):
        good = make_daily_df("2023-01-02", "2024-12-31")

        def fetch(code, period):
            if code == "BAD":
                raise SymbolNotFoundError("no data")
            return good

        fetcher = MagicMock()
        fetcher.fetch_ohlcv.side_effect = fetch
        monkeypatch.setattr("stock_trend_scorer.backtest.get_fetcher", lambda market: fetcher)

        # The second date's 6-month window runs past the end of the data.
        base_dates = [pd.Timestamp("2024-03-15"), pd.Timestamp("2024-09-15")]
        records, errors = bt.run_backtest(
            [("BAD", "US"), ("GOOD", "US")], scorer=TrendScorer(mode="discovery"), base_dates=base_dates
        )

        assert len(records) == 1
        assert {(e.code, e.base_date) for e in errors} == {("BAD", None), ("GOOD", "2024-09-15")}


class TestOutputShape:
    def test_records_flatten_to_one_row_with_indicator_columns(self):
        df = make_daily_df("2023-01-02", "2025-12-31")
        record = bt.evaluate_base_date("AAPL", "US", df, pd.Timestamp("2024-06-14"), TrendScorer(mode="discovery"))

        frame = bt.records_to_dataframe([record, record])

        assert len(frame) == 2
        for column in [
            "code", "market", "mode", "base_date", "base_price", "score", "classification",
            "max_price", "min_price", "end_price", "max_return_pct", "min_return_pct", "end_return_pct",
            "ind_ma_cross", "ind_rsi", "ind_macd", "ind_price_change", "ind_volume",
        ]:
            assert column in frame.columns


class TestSummarizeByScoreBand:
    def test_groups_returns_by_band(self):
        df = pd.DataFrame(
            {
                "score": [0.5, 0.45, 1.0, 0.1, -0.5],
                "end_return_pct": [10.0, -2.0, 6.0, 1.0, -3.0],
                "max_return_pct": [12.0, 1.0, 8.0, 2.0, 0.0],
                "min_return_pct": [-1.0, -5.0, -2.0, -1.0, -6.0],
            }
        )

        summary = bt.summarize_by_score_band(df, bands=[-1.0, 0.0, 0.4, 1.0])

        assert list(summary["count"]) == [1, 1, 3]
        top = summary.iloc[-1]
        assert top.name == "[+0.40, +1.00]"
        assert top["end_return_mean"] == pytest.approx(round((10 - 2 + 6) / 3, 2))
        assert top["win_rate_pct"] == pytest.approx(66.67)
        assert summary.iloc[0]["end_return_mean"] == pytest.approx(-3.0)
