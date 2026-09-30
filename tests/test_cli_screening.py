import pytest

from stock_trend_scorer.cli import run
from stock_trend_scorer.scoring import ScoreResult
from stock_trend_scorer.screening import ScreeningError, ScreeningResult


def make_result(code, market, total_score, classification):
    return ScreeningResult(
        market=market,
        score=ScoreResult(code=code, mode="discovery", total_score=total_score, classification=classification, indicators=[]),
    )


class TestScanCommand:
    def test_no_codes_returns_error(self, capsys):
        exit_code = run(["scan"])
        assert exit_code == 1
        assert "エラー" in capsys.readouterr().err

    def test_scores_given_codes_and_shows_candidate_count(self, monkeypatch, capsys):
        results = [
            make_result("AAPL", "US", 0.5, "上昇トレンド候補"),
            make_result("7203", "JP", -0.1, "様子見"),
        ]
        monkeypatch.setattr("stock_trend_scorer.cli.score_codes", lambda pairs, **kw: (results, []))

        exit_code = run(["scan", "AAPL", "7203"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "上昇トレンド候補 1件" in out
        assert "AAPL" in out and "7203" in out

    def test_reads_codes_from_file(self, tmp_path, monkeypatch, capsys):
        codes_file = tmp_path / "codes.txt"
        codes_file.write_text("AAPL\n# comment\nMSFT\n", encoding="utf-8")

        captured_pairs = {}

        def fake_score_codes(pairs, **kw):
            captured_pairs["pairs"] = pairs
            return [], []

        monkeypatch.setattr("stock_trend_scorer.cli.score_codes", fake_score_codes)

        run(["scan", "--codes-file", str(codes_file)])

        assert captured_pairs["pairs"] == [("AAPL", "US"), ("MSFT", "US")]

    def test_dedupes_codes(self, monkeypatch):
        captured_pairs = {}

        def fake_score_codes(pairs, **kw):
            captured_pairs["pairs"] = pairs
            return [], []

        monkeypatch.setattr("stock_trend_scorer.cli.score_codes", fake_score_codes)

        run(["scan", "AAPL", "aapl", "AAPL"])

        assert captured_pairs["pairs"] == [("AAPL", "US")]

    def test_errors_are_reported(self, monkeypatch, capsys):
        errors = [ScreeningError(code="BADCODE", market="US", message="no data")]
        monkeypatch.setattr("stock_trend_scorer.cli.score_codes", lambda pairs, **kw: ([], errors))

        run(["scan", "BADCODE"])
        out = capsys.readouterr().out

        assert "BADCODE" in out
        assert "no data" in out


class TestScanRandomOption:
    def test_random_and_codes_together_is_error(self, capsys):
        exit_code = run(["scan", "AAPL", "--random", "10", "--universe", "us"])
        assert exit_code == 1
        assert "同時に指定できません" in capsys.readouterr().err

    def test_random_and_codes_file_together_is_error(self, tmp_path, capsys):
        codes_file = tmp_path / "codes.txt"
        codes_file.write_text("AAPL\n", encoding="utf-8")
        exit_code = run(["scan", "--codes-file", str(codes_file), "--random", "10", "--universe", "us"])
        assert exit_code == 1
        assert "同時に指定できません" in capsys.readouterr().err

    def test_random_without_universe_is_error(self, capsys):
        exit_code = run(["scan", "--random", "10"])
        assert exit_code == 1
        assert "--universe" in capsys.readouterr().err

    def test_random_zero_is_error(self, capsys):
        exit_code = run(["scan", "--random", "0", "--universe", "us"])
        assert exit_code == 1
        assert "エラー" in capsys.readouterr().err

    def test_random_samples_from_universe(self, monkeypatch):
        monkeypatch.setattr("stock_trend_scorer.cli.load_universe", lambda market: ["A", "B", "C", "D", "E"])
        monkeypatch.setattr("stock_trend_scorer.cli.random.sample", lambda population, k: population[:k])

        captured = {}

        def fake_score_codes(pairs, **kw):
            captured["pairs"] = pairs
            return [], []

        monkeypatch.setattr("stock_trend_scorer.cli.score_codes", fake_score_codes)

        run(["scan", "--random", "3", "--universe", "us"])

        assert captured["pairs"] == [("A", "US"), ("B", "US"), ("C", "US")]

    def test_random_larger_than_universe_uses_whole_universe(self, monkeypatch):
        monkeypatch.setattr("stock_trend_scorer.cli.load_universe", lambda market: ["A", "B"])
        monkeypatch.setattr("stock_trend_scorer.cli.random.sample", lambda population, k: population[:k])

        captured = {}

        def fake_score_codes(pairs, **kw):
            captured["pairs"] = pairs
            return [], []

        monkeypatch.setattr("stock_trend_scorer.cli.score_codes", fake_score_codes)

        run(["scan", "--random", "50", "--universe", "jp"])

        assert captured["pairs"] == [("A", "JP"), ("B", "JP")]

    def test_universe_jp_uses_jp_market(self, monkeypatch):
        monkeypatch.setattr("stock_trend_scorer.cli.load_universe", lambda market: ["1000", "2000"])
        monkeypatch.setattr("stock_trend_scorer.cli.random.sample", lambda population, k: population[:k])

        captured = {}

        def fake_score_codes(pairs, **kw):
            captured["pairs"] = pairs
            return [], []

        monkeypatch.setattr("stock_trend_scorer.cli.score_codes", fake_score_codes)

        run(["scan", "--random", "2", "--universe", "jp"])

        assert captured["pairs"] == [("1000", "JP"), ("2000", "JP")]


class TestWatchCommand:
    def test_no_holdings_prints_message(self, tmp_path, capsys):
        exit_code = run(["--file", str(tmp_path / "holdings.json"), "watch"])
        assert exit_code == 0
        assert "保有銘柄はありません" in capsys.readouterr().out

    def test_shows_down_warning_count_for_holdings(self, tmp_path, monkeypatch, capsys):
        holdings_file = tmp_path / "holdings.json"
        run(["--file", str(holdings_file), "add", "7203"])

        results = [make_result("7203", "JP", -0.5, "下落トレンド警告")]
        monkeypatch.setattr("stock_trend_scorer.cli.score_codes", lambda pairs, **kw: (results, []))

        exit_code = run(["--file", str(holdings_file), "watch"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "下落トレンド警告 1件" in out
        assert "7203" in out

    def test_scores_with_is_held_true(self, tmp_path, monkeypatch):
        holdings_file = tmp_path / "holdings.json"
        run(["--file", str(holdings_file), "add", "7203"])

        captured = {}

        def fake_score_codes(pairs, **kw):
            captured.update(kw)
            return [], []

        monkeypatch.setattr("stock_trend_scorer.cli.score_codes", fake_score_codes)
        run(["--file", str(holdings_file), "watch"])

        assert captured["is_held"] is True


class TestBacktestCommand:
    @pytest.fixture
    def fake_backtest(self, monkeypatch):
        from stock_trend_scorer import backtest as bt

        captured = {}
        record = bt.BacktestRecord(
            code="AAPL", market="US", mode="discovery", base_date="2024-06-14", eval_end_date="2024-12-13",
            base_price=100.0, score=0.5, classification="上昇トレンド候補", max_price=120.0, min_price=95.0,
            end_price=110.0, max_return_pct=20.0, min_return_pct=-5.0, end_return_pct=10.0,
            week52_high_pct=-1.0, indicator_scores={"rsi": 0.3},
        )

        def fake_run_backtest(pairs, **kw):
            captured["pairs"] = pairs
            captured.update(kw)
            return [record], [bt.BacktestError(code="BAD", market="US", base_date=None, message="no data")]

        monkeypatch.setattr("stock_trend_scorer.cli.bt.run_backtest", fake_run_backtest)
        return captured

    def test_writes_csv_and_prints_summary(self, tmp_path, fake_backtest, capsys):
        import pandas as pd

        output = tmp_path / "out" / "bt.csv"
        exit_code = run(["backtest", "AAPL", "BAD", "--output", str(output)])
        out = capsys.readouterr().out

        assert exit_code == 0
        frame = pd.read_csv(output, encoding="utf-8-sig")
        assert frame.loc[0, "code"] == "AAPL"
        assert frame.loc[0, "end_return_pct"] == 10.0
        assert frame.loc[0, "ind_rsi"] == 0.3
        assert "スコア帯別サマリー" in out
        assert "BAD" in out and "no data" in out

    def test_default_uses_25_monthly_base_dates_and_discovery(self, tmp_path, fake_backtest):
        run(["backtest", "AAPL", "--output", str(tmp_path / "bt.csv")])

        assert fake_backtest["pairs"] == [("AAPL", "US")]
        assert len(fake_backtest["base_dates"]) == 25
        assert fake_backtest["horizon_months"] == 6
        assert fake_backtest["is_held"] is False
        assert fake_backtest["scorer"].mode == "discovery"

    def test_random_selection_is_shared_with_scan(self, tmp_path, monkeypatch, fake_backtest):
        monkeypatch.setattr("stock_trend_scorer.cli.load_universe", lambda market: ["1000", "2000", "3000"])
        monkeypatch.setattr("stock_trend_scorer.cli.random.sample", lambda population, k: population[:k])

        run(["backtest", "--random", "2", "--universe", "jp", "--output", str(tmp_path / "bt.csv")])

        assert fake_backtest["pairs"] == [("1000", "JP"), ("2000", "JP")]

    def test_no_codes_is_error(self, capsys):
        assert run(["backtest"]) == 1
        assert "エラー" in capsys.readouterr().err
