"""JSON-backed storage for the user's held stock codes.

Per the spec, only the stock code (+ market) is tracked — no quantity or
amount, and there is no brokerage integration.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Holding

DEFAULT_STORAGE_PATH = Path.home() / ".stock_trend_scorer" / "holdings.json"


class DuplicateHoldingError(Exception):
    """Raised when adding a holding that is already tracked."""


class HoldingNotFoundError(Exception):
    """Raised when removing a holding that isn't tracked."""


class AmbiguousHoldingError(Exception):
    """Raised when a code matches holdings in more than one market."""


class HoldingsRepository:
    """Manages the on-disk list of held stock codes (a JSON array of {code, market})."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_STORAGE_PATH

    def list(self) -> list[Holding]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Holding(code=item["code"], market=item["market"]) for item in data]

    def add(self, code: str, market: str) -> Holding:
        holdings = self.list()
        if any(h.code == code and h.market == market for h in holdings):
            raise DuplicateHoldingError(f"{code} ({market}) はすでに登録されています")

        holding = Holding(code=code, market=market)
        holdings.append(holding)
        self._save(holdings)
        return holding

    def remove(self, code: str, market: str | None = None) -> Holding:
        holdings = self.list()
        matches = [h for h in holdings if h.code == code and (market is None or h.market == market)]

        if not matches:
            raise HoldingNotFoundError(f"{code} は登録されていません")
        if len(matches) > 1:
            raise AmbiguousHoldingError(f"{code} は複数の市場に登録されています。--market で指定してください")

        target = matches[0]
        holdings.remove(target)
        self._save(holdings)
        return target

    def _save(self, holdings: list[Holding]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(h) for h in holdings]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
