"""Exceptions raised by price data fetchers."""

from __future__ import annotations


class DataFetchError(Exception):
    """Raised when price data could not be fetched due to a network/API error."""


class SymbolNotFoundError(DataFetchError):
    """Raised when no data is returned for the given symbol/code."""
