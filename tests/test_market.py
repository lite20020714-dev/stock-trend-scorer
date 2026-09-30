from stock_trend_scorer.market import detect_market, normalize_code


class TestDetectMarket:
    def test_numeric_code_is_jp(self):
        assert detect_market("7203") == "JP"

    def test_alpha_code_is_us(self):
        assert detect_market("AAPL") == "US"

    def test_strips_whitespace_before_checking(self):
        assert detect_market(" 7203 ") == "JP"


class TestNormalizeCode:
    def test_us_code_is_uppercased(self):
        assert normalize_code("aapl", "US") == "AAPL"

    def test_jp_code_is_left_as_is(self):
        assert normalize_code("7203", "JP") == "7203"

    def test_strips_whitespace(self):
        assert normalize_code(" aapl ", "US") == "AAPL"
