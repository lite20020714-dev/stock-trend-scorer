"""Infers a stock's market from its code when the user doesn't specify one."""

from __future__ import annotations


def detect_market(code: str) -> str:
    """JP codes are numeric (e.g. "7203"); anything else is treated as a US ticker."""
    return "JP" if code.strip().isdigit() else "US"


def normalize_code(code: str, market: str) -> str:
    code = code.strip()
    return code.upper() if market == "US" else code
