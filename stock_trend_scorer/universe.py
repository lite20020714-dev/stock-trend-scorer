"""Stock universe (index constituent) lists used by `scan --random`.

Bundled CSV snapshots ship with the package so random scanning works
offline without any extra setup:
  - US: S&P 500 constituents (data/universe/sp500.csv)
  - JP: JPX日経400 constituents (data/universe/jpx400.csv)

Both were captured from public sources (Wikipedia) and will drift out of
date as index membership changes; pass `path` to point at a refreshed CSV
(columns: code, name) without touching code.
"""

from __future__ import annotations

import csv
from importlib import resources
from pathlib import Path

UNIVERSE_FILES = {
    "US": "sp500.csv",
    "JP": "jpx400.csv",
}


def load_universe(market: str, path: str | Path | None = None) -> list[str]:
    """Return the stock codes making up `market`'s universe.

    `market` is "US" or "JP". If `path` is omitted, the bundled CSV for
    that market is used.
    """
    market = market.upper()
    if market not in UNIVERSE_FILES:
        raise ValueError(f"Unsupported market: {market!r}. Use one of {list(UNIVERSE_FILES)}")

    if path is not None:
        return _read_codes(Path(path))

    package_dir = resources.files("stock_trend_scorer.data") / "universe" / UNIVERSE_FILES[market]
    with resources.as_file(package_dir) as csv_path:
        return _read_codes(csv_path)


def _read_codes(path: Path) -> list[str]:
    with open(path, encoding="utf-8", newline="") as f:
        return [row["code"] for row in csv.DictReader(f)]
