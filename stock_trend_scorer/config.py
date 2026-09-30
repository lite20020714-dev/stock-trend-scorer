"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    jquants_mail_address: str | None
    jquants_password: str | None
    jquants_refresh_token: str | None
    jp_data_source: str  # "yfinance" or "jquants"


def load_settings() -> Settings:
    return Settings(
        jquants_mail_address=os.environ.get("JQUANTS_MAIL_ADDRESS"),
        jquants_password=os.environ.get("JQUANTS_PASSWORD"),
        jquants_refresh_token=os.environ.get("JQUANTS_REFRESH_TOKEN"),
        jp_data_source=os.environ.get("JP_DATA_SOURCE", "yfinance"),
    )
