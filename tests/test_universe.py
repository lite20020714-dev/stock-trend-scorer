import csv

import pytest

from stock_trend_scorer.universe import load_universe


class TestLoadUniverseBundled:
    def test_us_universe_is_sp500_sized(self):
        codes = load_universe("US")
        assert len(codes) > 400
        assert "AAPL" in codes

    def test_jp_universe_has_400_codes(self):
        codes = load_universe("JP")
        assert len(codes) == 400
        assert "7203" in codes

    def test_market_is_case_insensitive(self):
        assert load_universe("us") == load_universe("US")

    def test_unsupported_market_raises(self):
        with pytest.raises(ValueError):
            load_universe("EU")

    def test_no_duplicate_codes(self):
        codes = load_universe("US")
        assert len(codes) == len(set(codes))


class TestLoadUniverseFromPath:
    def test_reads_codes_from_custom_csv(self, tmp_path):
        path = tmp_path / "custom.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["code", "name"])
            writer.writerow(["1234", "テスト銘柄"])
            writer.writerow(["5678", "テスト銘柄2"])

        codes = load_universe("JP", path=path)
        assert codes == ["1234", "5678"]
