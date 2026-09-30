from unittest.mock import MagicMock

import pandas as pd
import pytest

from stock_trend_scorer.data.exceptions import SymbolNotFoundError
from stock_trend_scorer.scoring import ScoreResult, TrendScorer
from stock_trend_scorer.screening import score_codes


@pytest.fixture
def fake_scorer():
    scorer = MagicMock(spec=TrendScorer)

    def fake_score(code, df, is_held=False):
        return ScoreResult(code=code, mode="discovery", total_score=0.5, classification="上昇トレンド候補", indicators=[])

    scorer.score.side_effect = fake_score
    return scorer


class TestScoreCodes:
    def test_scores_each_code_with_its_own_fetcher(self, monkeypatch, fake_scorer):
        fetcher = MagicMock()
        fetcher.fetch_ohlcv.return_value = pd.DataFrame({"close": [1, 2, 3]})
        monkeypatch.setattr("stock_trend_scorer.screening.get_fetcher", lambda market: fetcher)

        results, errors = score_codes([("AAPL", "US"), ("MSFT", "US")], scorer=fake_scorer)

        assert len(results) == 2
        assert errors == []
        assert {r.score.code for r in results} == {"AAPL", "MSFT"}
        assert all(r.market == "US" for r in results)

    def test_fetcher_created_once_per_market(self, monkeypatch, fake_scorer):
        created_markets = []

        def make_fetcher(market):
            created_markets.append(market)
            fetcher = MagicMock()
            fetcher.fetch_ohlcv.return_value = pd.DataFrame({"close": [1, 2, 3]})
            return fetcher

        monkeypatch.setattr("stock_trend_scorer.screening.get_fetcher", make_fetcher)

        score_codes([("AAPL", "US"), ("MSFT", "US"), ("7203", "JP")], scorer=fake_scorer)

        assert created_markets == ["US", "JP"]

    def test_fetch_failure_collected_as_error_not_raised(self, monkeypatch, fake_scorer):
        fetcher = MagicMock()
        fetcher.fetch_ohlcv.side_effect = SymbolNotFoundError("no data")
        monkeypatch.setattr("stock_trend_scorer.screening.get_fetcher", lambda market: fetcher)

        results, errors = score_codes([("BADCODE", "US")], scorer=fake_scorer)

        assert results == []
        assert len(errors) == 1
        assert errors[0].code == "BADCODE"
        assert "no data" in errors[0].message

    def test_scoring_failure_collected_as_error(self, monkeypatch):
        fetcher = MagicMock()
        fetcher.fetch_ohlcv.return_value = pd.DataFrame({"close": [1, 2, 3]})
        monkeypatch.setattr("stock_trend_scorer.screening.get_fetcher", lambda market: fetcher)

        scorer = MagicMock(spec=TrendScorer)
        scorer.score.side_effect = ValueError("not enough data")

        results, errors = score_codes([("AAPL", "US")], scorer=scorer)

        assert results == []
        assert len(errors) == 1
        assert "not enough data" in errors[0].message

    def test_is_held_and_period_passed_through(self, monkeypatch, fake_scorer):
        fetcher = MagicMock()
        fetcher.fetch_ohlcv.return_value = pd.DataFrame({"close": [1, 2, 3]})
        monkeypatch.setattr("stock_trend_scorer.screening.get_fetcher", lambda market: fetcher)

        score_codes([("AAPL", "US")], scorer=fake_scorer, is_held=True, period="1y")

        fetcher.fetch_ohlcv.assert_called_once_with("AAPL", period="1y")
        fake_scorer.score.assert_called_once()
        assert fake_scorer.score.call_args.kwargs["is_held"] is True
