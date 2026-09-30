"""Data model for a tracked holding: a stock code only (no quantity/amount)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Holding:
    code: str
    market: str  # "JP" or "US"
