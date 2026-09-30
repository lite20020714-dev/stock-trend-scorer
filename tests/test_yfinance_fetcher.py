import pandas as pd
import pytest

from stock_trend_scorer.data.exceptions import DataFetchError, SymbolNotFoundError
from stock_trend_scorer.data.yfinance_fetcher import YFinanceFetcher, normalize_jp_code


class TestNormalizeJpCode:
    def test_appends_suffix(self):
        assert normalize_jp_code("7203") == "7203.T"

    def test_leaves_existing_suffix(self):
        assert normalize_jp_code("7203.T") == "7203.T"

    def test_strips_and_uppercases(self):
        assert normalize_jp_code(" 7203 ") == "7203.T"


class TestYFinanceFetcherInit:
    def test_rejects_unknown_market(self):
        with pytest.raises(ValueError):
            YFinanceFetcher(market="XX")


class TestFetchOhlcvUsMarket:
    def test_resolves_symbol_and_returns_normalized_columns(self, monkeypatch, sample_ohlcv_df):
        captured = {}

        def fake_download(symbol, **kwargs):
            captured["symbol"] = symbol
            captured["kwargs"] = kwargs
            return sample_ohlcv_df

        monkeypatch.setattr("stock_trend_scorer.data.yfinance_fetcher.yf.download", fake_download)

        fetcher = YFinanceFetcher(market="US")
        result = fetcher.fetch_ohlcv("aapl", period="6mo", interval="1d")

        assert captured["symbol"] == "AAPL"
        assert captured["kwargs"]["period"] == "6mo"
        assert captured["kwargs"]["interval"] == "1d"
        assert list(result.columns) == ["open", "high", "low", "close", "volume"]
        assert result.index.name == "date"
        assert len(result) == 3

    def test_empty_result_raises_symbol_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "stock_trend_scorer.data.yfinance_fetcher.yf.download",
            lambda symbol, **kwargs: pd.DataFrame(),
        )
        fetcher = YFinanceFetcher(market="US")
        with pytest.raises(SymbolNotFoundError):
            fetcher.fetch_ohlcv("NOSUCHTICKER")

    def test_download_exception_wrapped_as_data_fetch_error(self, monkeypatch):
        def raise_error(symbol, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr("stock_trend_scorer.data.yfinance_fetcher.yf.download", raise_error)
        fetcher = YFinanceFetcher(market="US")
        with pytest.raises(DataFetchError):
            fetcher.fetch_ohlcv("AAPL")

    def test_multiindex_columns_are_flattened(self, monkeypatch, sample_ohlcv_df):
        multi_df = sample_ohlcv_df.copy()
        multi_df.columns = pd.MultiIndex.from_product([multi_df.columns, ["AAPL"]])
        monkeypatch.setattr(
            "stock_trend_scorer.data.yfinance_fetcher.yf.download",
            lambda symbol, **kwargs: multi_df,
        )
        fetcher = YFinanceFetcher(market="US")
        result = fetcher.fetch_ohlcv("AAPL")
        assert list(result.columns) == ["open", "high", "low", "close", "volume"]


class TestFetchOhlcvJpMarket:
    def test_normalizes_jp_code_before_download(self, monkeypatch, sample_ohlcv_df):
        captured = {}

        def fake_download(symbol, **kwargs):
            captured["symbol"] = symbol
            return sample_ohlcv_df

        monkeypatch.setattr("stock_trend_scorer.data.yfinance_fetcher.yf.download", fake_download)

        fetcher = YFinanceFetcher(market="JP")
        fetcher.fetch_ohlcv("7203")

        assert captured["symbol"] == "7203.T"
