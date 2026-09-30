import pytest

from stock_trend_scorer.portfolio.models import Holding
from stock_trend_scorer.portfolio.repository import (
    AmbiguousHoldingError,
    DuplicateHoldingError,
    HoldingNotFoundError,
    HoldingsRepository,
)


@pytest.fixture
def repo(tmp_path):
    return HoldingsRepository(path=tmp_path / "holdings.json")


class TestList:
    def test_empty_when_file_does_not_exist(self, repo):
        assert repo.list() == []


class TestAdd:
    def test_add_returns_and_persists_holding(self, repo):
        holding = repo.add("7203", "JP")
        assert holding == Holding(code="7203", market="JP")
        assert repo.list() == [Holding(code="7203", market="JP")]

    def test_add_persists_across_repository_instances(self, tmp_path):
        path = tmp_path / "holdings.json"
        HoldingsRepository(path=path).add("AAPL", "US")
        reloaded = HoldingsRepository(path=path)
        assert reloaded.list() == [Holding(code="AAPL", market="US")]

    def test_duplicate_add_raises(self, repo):
        repo.add("7203", "JP")
        with pytest.raises(DuplicateHoldingError):
            repo.add("7203", "JP")

    def test_same_code_different_market_is_allowed(self, repo):
        repo.add("7203", "JP")
        repo.add("7203", "US")
        assert len(repo.list()) == 2


class TestRemove:
    def test_remove_existing_holding(self, repo):
        repo.add("7203", "JP")
        removed = repo.remove("7203", "JP")
        assert removed == Holding(code="7203", market="JP")
        assert repo.list() == []

    def test_remove_without_market_matches_single_holding(self, repo):
        repo.add("7203", "JP")
        repo.remove("7203")
        assert repo.list() == []

    def test_remove_nonexistent_raises(self, repo):
        with pytest.raises(HoldingNotFoundError):
            repo.remove("7203")

    def test_remove_ambiguous_without_market_raises(self, repo):
        repo.add("7203", "JP")
        repo.add("7203", "US")
        with pytest.raises(AmbiguousHoldingError):
            repo.remove("7203")

    def test_remove_ambiguous_resolved_with_market(self, repo):
        repo.add("7203", "JP")
        repo.add("7203", "US")
        repo.remove("7203", "JP")
        assert repo.list() == [Holding(code="7203", market="US")]
