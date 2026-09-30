import pytest

from stock_trend_scorer.data.factory import get_fetcher
from stock_trend_scorer.data.jquants_fetcher import JQuantsFetcher
from stock_trend_scorer.data.yfinance_fetcher import YFinanceFetcher


class TestGetFetcher:
    def test_us_market_returns_yfinance_fetcher(self, monkeypatch):
        monkeypatch.delenv("JP_DATA_SOURCE", raising=False)
        fetcher = get_fetcher("US")
        assert isinstance(fetcher, YFinanceFetcher)
        assert fetcher.market == "US"

    def test_jp_market_defaults_to_yfinance(self, monkeypatch):
        monkeypatch.delenv("JP_DATA_SOURCE", raising=False)
        fetcher = get_fetcher("JP")
        assert isinstance(fetcher, YFinanceFetcher)
        assert fetcher.market == "JP"

    def test_jp_market_uses_jquants_when_configured(self, monkeypatch):
        monkeypatch.setenv("JP_DATA_SOURCE", "jquants")
        monkeypatch.setenv("JQUANTS_REFRESH_TOKEN", "rt")
        fetcher = get_fetcher("jp")
        assert isinstance(fetcher, JQuantsFetcher)

    def test_unsupported_market_raises(self):
        with pytest.raises(ValueError):
            get_fetcher("EU")
