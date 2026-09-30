from unittest.mock import MagicMock

import pytest

from stock_trend_scorer.data.exceptions import DataFetchError, SymbolNotFoundError
from stock_trend_scorer.data.jquants_fetcher import JQuantsFetcher


def make_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


SAMPLE_QUOTES = {
    "daily_quotes": [
        {
            "Date": "2024-01-01",
            "Code": "72030",
            "Open": 100.0,
            "High": 105.0,
            "Low": 99.0,
            "Close": 104.0,
            "Volume": 1000,
        },
        {
            "Date": "2024-01-02",
            "Code": "72030",
            "Open": 101.0,
            "High": 106.0,
            "Low": 100.0,
            "Close": 105.0,
            "Volume": 1100,
        },
    ]
}


class TestInit:
    def test_missing_credentials_raises(self, monkeypatch):
        monkeypatch.delenv("JQUANTS_MAIL_ADDRESS", raising=False)
        monkeypatch.delenv("JQUANTS_PASSWORD", raising=False)
        monkeypatch.delenv("JQUANTS_REFRESH_TOKEN", raising=False)
        with pytest.raises(DataFetchError):
            JQuantsFetcher()

    def test_refresh_token_alone_is_sufficient(self):
        fetcher = JQuantsFetcher(refresh_token="rt")
        assert fetcher._refresh_token == "rt"

    def test_mail_and_password_are_sufficient(self):
        fetcher = JQuantsFetcher(mail_address="a@example.com", password="pw")
        assert fetcher._mail_address == "a@example.com"


class TestFetchOhlcv:
    def test_full_auth_flow_and_data_fetch(self):
        session = MagicMock()
        session.post.side_effect = [
            make_response(json_data={"refreshToken": "rt-123"}),
            make_response(json_data={"idToken": "id-456"}),
        ]
        session.get.return_value = make_response(json_data=SAMPLE_QUOTES)

        fetcher = JQuantsFetcher(mail_address="a@example.com", password="pw", session=session)
        df = fetcher.fetch_ohlcv("7203", period="1y")

        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 2
        assert df.index.name == "date"

        auth_user_call = session.post.call_args_list[0]
        assert auth_user_call.kwargs["json"] == {"mailaddress": "a@example.com", "password": "pw"}

        auth_refresh_call = session.post.call_args_list[1]
        assert auth_refresh_call.kwargs["params"] == {"refreshtoken": "rt-123"}

        get_call = session.get.call_args
        assert get_call.kwargs["headers"] == {"Authorization": "Bearer id-456"}
        assert get_call.kwargs["params"]["code"] == "7203"

    def test_refresh_token_skips_auth_user_step(self):
        session = MagicMock()
        session.post.return_value = make_response(json_data={"idToken": "id-456"})
        session.get.return_value = make_response(json_data=SAMPLE_QUOTES)

        fetcher = JQuantsFetcher(refresh_token="rt-existing", session=session)
        fetcher.fetch_ohlcv("7203")

        assert session.post.call_count == 1
        assert session.post.call_args.kwargs["params"] == {"refreshtoken": "rt-existing"}

    def test_id_token_is_cached_across_calls(self):
        session = MagicMock()
        session.post.return_value = make_response(json_data={"idToken": "id-456"})
        session.get.return_value = make_response(json_data=SAMPLE_QUOTES)

        fetcher = JQuantsFetcher(refresh_token="rt-existing", session=session)
        fetcher.fetch_ohlcv("7203")
        fetcher.fetch_ohlcv("7203")

        assert session.post.call_count == 1
        assert session.get.call_count == 2

    def test_empty_quotes_raises_symbol_not_found(self):
        session = MagicMock()
        session.post.return_value = make_response(json_data={"idToken": "id-456"})
        session.get.return_value = make_response(json_data={"daily_quotes": []})

        fetcher = JQuantsFetcher(refresh_token="rt", session=session)
        with pytest.raises(SymbolNotFoundError):
            fetcher.fetch_ohlcv("7203")

    def test_auth_failure_raises_data_fetch_error(self):
        session = MagicMock()
        session.post.return_value = make_response(status_code=401, text="unauthorized")

        fetcher = JQuantsFetcher(mail_address="a@example.com", password="wrong", session=session)
        with pytest.raises(DataFetchError):
            fetcher.fetch_ohlcv("7203")

    def test_data_request_failure_raises_data_fetch_error(self):
        session = MagicMock()
        session.post.return_value = make_response(json_data={"idToken": "id-456"})
        session.get.return_value = make_response(status_code=500, text="server error")

        fetcher = JQuantsFetcher(refresh_token="rt", session=session)
        with pytest.raises(DataFetchError):
            fetcher.fetch_ohlcv("7203")

    def test_non_daily_interval_rejected(self):
        fetcher = JQuantsFetcher(refresh_token="rt")
        with pytest.raises(ValueError):
            fetcher.fetch_ohlcv("7203", interval="1wk")
