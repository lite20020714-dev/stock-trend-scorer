"""OHLCV fetcher backed by the J-Quants API (J-Quants 日次株価 API).

Authentication is a two-step token exchange:
  1. mailaddress/password -> refreshToken (POST /v1/token/auth_user)
  2. refreshToken -> idToken            (POST /v1/token/auth_refresh)
The idToken is then sent as a Bearer token on data requests.

Credentials can be supplied directly or via environment variables:
  JQUANTS_MAIL_ADDRESS, JQUANTS_PASSWORD, JQUANTS_REFRESH_TOKEN
(JQUANTS_REFRESH_TOKEN, if set, skips the mail/password auth step).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pandas as pd
import requests

from .base import OHLCV_COLUMNS, PriceFetcher
from .exceptions import DataFetchError, SymbolNotFoundError

BASE_URL = "https://api.jquants.com/v1"

_PERIOD_TO_DAYS = {
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
    "2y": 730,
    "5y": 1825,
    "10y": 3650,
}

_QUOTE_COLUMN_MAP = {
    "Date": "date",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
}


class JQuantsFetcher(PriceFetcher):
    """Fetches JP stock OHLCV data via the J-Quants API."""

    def __init__(
        self,
        mail_address: str | None = None,
        password: str | None = None,
        refresh_token: str | None = None,
        session: requests.Session | None = None,
    ):
        self._mail_address = mail_address or os.environ.get("JQUANTS_MAIL_ADDRESS")
        self._password = password or os.environ.get("JQUANTS_PASSWORD")
        self._refresh_token = refresh_token or os.environ.get("JQUANTS_REFRESH_TOKEN")
        self._session = session or requests.Session()
        self._id_token: str | None = None

        if not self._refresh_token and not (self._mail_address and self._password):
            raise DataFetchError(
                "J-Quants credentials not found. Set JQUANTS_REFRESH_TOKEN, or both "
                "JQUANTS_MAIL_ADDRESS and JQUANTS_PASSWORD."
            )

    def _fetch_refresh_token(self) -> str:
        if self._refresh_token:
            return self._refresh_token
        resp = self._session.post(
            f"{BASE_URL}/token/auth_user",
            json={"mailaddress": self._mail_address, "password": self._password},
        )
        if resp.status_code != 200:
            raise DataFetchError(f"J-Quants authentication failed: {resp.status_code} {resp.text}")
        self._refresh_token = resp.json()["refreshToken"]
        return self._refresh_token

    def _fetch_id_token(self) -> str:
        if self._id_token:
            return self._id_token
        refresh_token = self._fetch_refresh_token()
        resp = self._session.post(
            f"{BASE_URL}/token/auth_refresh",
            params={"refreshtoken": refresh_token},
        )
        if resp.status_code != 200:
            raise DataFetchError(f"J-Quants token refresh failed: {resp.status_code} {resp.text}")
        self._id_token = resp.json()["idToken"]
        return self._id_token

    def fetch_ohlcv(self, code: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        if interval != "1d":
            raise ValueError("JQuantsFetcher only supports the '1d' interval")

        id_token = self._fetch_id_token()
        from_date = self._resolve_from_date(period)

        resp = self._session.get(
            f"{BASE_URL}/prices/daily_quotes",
            headers={"Authorization": f"Bearer {id_token}"},
            params={"code": code.strip(), "from": from_date},
        )
        if resp.status_code != 200:
            raise DataFetchError(f"Failed to fetch data for {code}: {resp.status_code} {resp.text}")

        quotes = resp.json().get("daily_quotes", [])
        if not quotes:
            raise SymbolNotFoundError(f"No data returned for {code}")

        df = pd.DataFrame(quotes).rename(columns=_QUOTE_COLUMN_MAP)
        missing = set(_QUOTE_COLUMN_MAP.values()) - set(df.columns)
        if missing:
            raise DataFetchError(f"Missing columns {sorted(missing)} for {code}")

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df[OHLCV_COLUMNS].astype(float)
        # Trading-halt / suspended days can come back with null OHLCV fields;
        # drop them rather than let NaN poison every downstream calculation.
        df = df.dropna()
        if df.empty:
            raise SymbolNotFoundError(f"No usable (non-NaN) data returned for {code}")
        return df

    @staticmethod
    def _resolve_from_date(period: str) -> str:
        days = _PERIOD_TO_DAYS.get(period, 365)
        return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
