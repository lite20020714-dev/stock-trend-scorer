import pytest

from stock_trend_scorer.cli import run
from stock_trend_scorer.portfolio.repository import HoldingsRepository


@pytest.fixture
def holdings_file(tmp_path):
    return tmp_path / "holdings.json"


class TestAddCommand:
    def test_add_jp_code_auto_detected(self, holdings_file, capsys):
        exit_code = run(["--file", str(holdings_file), "add", "7203"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "7203" in out and "JP" in out
        assert HoldingsRepository(holdings_file).list()[0].market == "JP"

    def test_add_us_code_auto_detected_and_uppercased(self, holdings_file):
        run(["--file", str(holdings_file), "add", "aapl"])
        holding = HoldingsRepository(holdings_file).list()[0]
        assert holding.code == "AAPL"
        assert holding.market == "US"

    def test_add_with_explicit_market_override(self, holdings_file):
        run(["--file", str(holdings_file), "add", "7203", "--market", "US"])
        holding = HoldingsRepository(holdings_file).list()[0]
        assert holding.market == "US"

    def test_add_duplicate_returns_error_exit_code(self, holdings_file, capsys):
        run(["--file", str(holdings_file), "add", "7203"])
        exit_code = run(["--file", str(holdings_file), "add", "7203"])
        assert exit_code == 1
        assert "エラー" in capsys.readouterr().err


class TestRemoveCommand:
    def test_remove_existing(self, holdings_file):
        run(["--file", str(holdings_file), "add", "7203"])
        exit_code = run(["--file", str(holdings_file), "remove", "7203"])
        assert exit_code == 0
        assert HoldingsRepository(holdings_file).list() == []

    def test_remove_nonexistent_returns_error_exit_code(self, holdings_file, capsys):
        exit_code = run(["--file", str(holdings_file), "remove", "7203"])
        assert exit_code == 1
        assert "エラー" in capsys.readouterr().err


class TestListCommand:
    def test_list_empty(self, holdings_file, capsys):
        exit_code = run(["--file", str(holdings_file), "list"])
        assert exit_code == 0
        assert "保有銘柄はありません" in capsys.readouterr().out

    def test_list_shows_added_holdings(self, holdings_file, capsys):
        run(["--file", str(holdings_file), "add", "7203"])
        run(["--file", str(holdings_file), "add", "aapl"])
        capsys.readouterr()
        run(["--file", str(holdings_file), "list"])
        out = capsys.readouterr().out
        assert "7203" in out
        assert "AAPL" in out
