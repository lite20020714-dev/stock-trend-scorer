import json

import pytest

from stock_trend_scorer.scoring.weights import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, load_scoring_config


class TestLoadScoringConfig:
    def test_no_path_returns_defaults(self):
        config = load_scoring_config()
        assert config.weights == DEFAULT_WEIGHTS
        assert config.thresholds == DEFAULT_THRESHOLDS

    def test_partial_override_merges_with_defaults(self, tmp_path):
        path = tmp_path / "weights.json"
        path.write_text(json.dumps({"weights": {"rsi": 2.0}, "thresholds": {"up": 0.5}}), encoding="utf-8")

        config = load_scoring_config(path)

        assert config.weights["rsi"] == 2.0
        assert config.weights["macd"] == DEFAULT_WEIGHTS["macd"]
        assert config.thresholds["up"] == 0.5
        assert config.thresholds["down"] == DEFAULT_THRESHOLDS["down"]

    def test_defaults_are_not_mutated_by_override(self, tmp_path):
        path = tmp_path / "weights.json"
        path.write_text(json.dumps({"weights": {"rsi": 2.0}}), encoding="utf-8")

        load_scoring_config(path)

        assert DEFAULT_WEIGHTS["rsi"] == 1.0
