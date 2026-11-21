"""Tests for app.stocks."""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from app import stocks
from app.stocks import Quote, _fetch_quote, _quote_from_meta, clean_symbols, get_stocks, quote_to_dict


def _meta(**overrides):
    """Build a Yahoo Finance chart meta object with test values."""
    meta = {
        "symbol": "AAPL",
        "longName": "Apple Inc.",
        "regularMarketPrice": 342.56,
        "chartPreviousClose": 350.0,
        "regularMarketChangePercent": -2.12,
        "regularMarketDayHigh": 354.3,
        "regularMarketDayLow": 340.56,
        "regularMarketVolume": 80450240,
        "regularMarketTime": 1795208402,
        "exchangeTimezoneName": "America/New_York",
    }
    meta.update(overrides)
    return meta


def _chart_payload(meta):
    """Wrap a meta object in a Yahoo Finance chart response."""
    return {"chart": {"result": [{"meta": meta}], "error": None}}


class FakeRedis:
    """In-memory stand-in for the Redis client."""

    def __init__(self):
        """Initialize an empty store."""
        self.store = {}
        self.saves = 0

    def get_entry(self, key):
        """Return the stored value, or None."""
        return self.store.get(key)

    def save_entry(self, key, value, expiration=None):
        """Store the value."""
        self.store[key] = value
        self.saves += 1


class TestCleanSymbols(unittest.TestCase):
    """Tests for clean_symbols."""

    def test_valid_list_uppercased(self):
        """A comma list is split and uppercased."""
        self.assertEqual(clean_symbols("aapl, msft"), ["AAPL", "MSFT"])

    def test_invalid_dropped(self):
        """Symbols with bad characters are dropped."""
        self.assertEqual(clean_symbols("AAPL, !!!, MSFT"), ["AAPL", "MSFT"])

    def test_dots_and_dashes_kept(self):
        """Dots and dashes are valid in tickers like BRK.B."""
        self.assertEqual(clean_symbols("brk.b, brk-b"), ["BRK.B", "BRK-B"])

    def test_duplicates_removed(self):
        """Repeated symbols appear once."""
        self.assertEqual(clean_symbols("aapl, AAPL, msft"), ["AAPL", "MSFT"])

    def test_empty_and_none(self):
        """Empty or missing input gives an empty list."""
        self.assertEqual(clean_symbols(""), [])
        self.assertEqual(clean_symbols(None), [])

    def test_capped_at_twenty(self):
        """More than twenty symbols are capped."""
        many = ",".join(f"S{i}" for i in range(25))
        self.assertEqual(len(clean_symbols(many)), 20)


class TestQuoteFromMeta(unittest.TestCase):
    """Tests for _quote_from_meta."""

    def test_fields_and_computed_change(self):
        """Meta fields map onto the quote and change is computed."""
        quote = _quote_from_meta("AAPL", _meta())
        self.assertEqual(quote.symbol, "AAPL")
        self.assertEqual(quote.name, "Apple Inc.")
        self.assertEqual(quote.price, 342.56)
        self.assertEqual(quote.previous_close, 350.0)
        self.assertEqual(quote.change, -7.44)
        self.assertEqual(quote.change_percent, -2.12)
        self.assertEqual(quote.day_high, 354.3)
        self.assertEqual(quote.day_low, 340.56)
        self.assertEqual(quote.volume, 80450240)
        self.assertEqual(quote.as_of.isoformat(), "2026-11-20T21:00:02+00:00")
        self.assertIsNone(quote.error)

    def test_missing_fields_become_none(self):
        """A bare meta object gives a quote with no values."""
        quote = _quote_from_meta("AAPL", {"symbol": "AAPL"})
        self.assertIsNone(quote.name)
        self.assertIsNone(quote.price)
        self.assertIsNone(quote.change)
        self.assertIsNone(quote.as_of)

    def test_change_percent_computed_when_missing(self):
        """Change percent is computed when the API omits it."""
        quote = _quote_from_meta("AAPL", _meta(regularMarketChangePercent=None))
        self.assertAlmostEqual(quote.change_percent, -2.13, places=2)


class TestQuoteRoundTrip(unittest.TestCase):
    """Tests for quote_to_dict and cache restore."""

    def test_dict_round_trip(self):
        """A quote survives conversion to a dict and back."""
        quote = _quote_from_meta("AAPL", _meta())
        restored = stocks._quote_from_dict(quote_to_dict(quote))
        self.assertEqual(restored, quote)


class TestFetchQuote(unittest.TestCase):
    """Tests for _fetch_quote with a mocked network."""

    def _mock_urlopen(self, payload):
        """Return a urlopen mock serving the given JSON payload."""
        body = io.BytesIO(json.dumps(payload).encode("utf-8"))
        return patch("urllib.request.urlopen", return_value=body)

    def test_success(self):
        """A chart response becomes a quote."""
        with self._mock_urlopen(_chart_payload(_meta())):
            quote = _fetch_quote("AAPL")
        self.assertEqual(quote.symbol, "AAPL")
        self.assertEqual(quote.price, 342.56)
        self.assertIsNone(quote.error)

    def test_not_found_error(self):
        """A chart error becomes a not_found quote."""
        payload = {"chart": {"result": None, "error": {"code": "Not Found"}}}
        with self._mock_urlopen(payload):
            quote = _fetch_quote("ZZZZQQQ")
        self.assertEqual(quote.error, "not_found")
        self.assertIsNone(quote.price)

    def test_http_404(self):
        """An HTTP 404 becomes a not_found quote."""
        error = urllib.error.HTTPError("http://x", 404, "Not Found", hdrs=None, fp=None)
        with patch("urllib.request.urlopen", side_effect=error):
            quote = _fetch_quote("ZZZZQQQ")
        self.assertEqual(quote.error, "not_found")

    def test_http_429_is_unavailable(self):
        """An HTTP 429 becomes an unavailable quote, not not_found."""
        error = urllib.error.HTTPError("http://x", 429, "Too Many Requests", hdrs=None, fp=None)
        with patch("urllib.request.urlopen", side_effect=error):
            quote = _fetch_quote("AAPL")
        self.assertEqual(quote.error, "unavailable")

    def test_network_failure_is_unavailable(self):
        """A network failure becomes an unavailable quote."""
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            quote = _fetch_quote("AAPL")
        self.assertEqual(quote.error, "unavailable")


class TestGetStocks(unittest.TestCase):
    """Tests for get_stocks caching and defaults."""

    def test_cache_hit_skips_fetch(self):
        """A cached result is returned without fetching."""
        fake = FakeRedis()
        quote = _quote_from_meta("AAPL", _meta())
        fake.save_entry("stocks:AAPL", [quote_to_dict(quote)], expiration=120)
        with patch.object(stocks, "REDIS_CLIENT", fake):
            with patch.object(stocks, "_fetch_quote", side_effect=AssertionError("should not fetch")):
                result = get_stocks(["AAPL"])
        self.assertEqual(result, [quote])

    def test_cache_miss_fetches_and_saves(self):
        """A cache miss fetches live and stores the result."""
        fake = FakeRedis()
        quote = _quote_from_meta("MSFT", _meta(symbol="MSFT", longName="Microsoft Corporation"))
        with patch.object(stocks, "REDIS_CLIENT", fake):
            with patch.object(stocks, "_fetch_quote", return_value=quote) as fetch:
                result = get_stocks(["MSFT"])
                fetch.assert_called_once_with("MSFT")
        self.assertEqual(result, [quote])
        self.assertIn("stocks:MSFT", fake.store)

    def test_no_symbols_uses_default_watchlist(self):
        """No symbols means the default watchlist is fetched."""
        fake = FakeRedis()
        empty_quote = Quote("X", None, None, None, None, None, None, None, None, None)
        with patch.object(stocks, "REDIS_CLIENT", fake):
            with patch.object(stocks, "_fetch_quote", return_value=empty_quote) as fetch:
                get_stocks(None)
                fetched = [call.args[0] for call in fetch.call_args_list]
        self.assertEqual(fetched, stocks.DEFAULT_SYMBOLS)

    def test_empty_list_returns_empty(self):
        """An empty symbol list returns no quotes."""
        self.assertEqual(get_stocks([]), [])

    def test_redis_down_falls_back_to_live(self):
        """A dead cache degrades to a live fetch instead of raising."""
        class BrokenRedis:
            """Redis client that always fails."""

            def get_entry(self, key):
                """Raise on read."""
                raise KeyError("down")

            def save_entry(self, key, value, expiration=None):
                """Raise on write."""
                raise Exception("down")

        quote = _quote_from_meta("AAPL", _meta())
        with patch.object(stocks, "REDIS_CLIENT", BrokenRedis()):
            with patch.object(stocks, "_fetch_quote", return_value=quote):
                self.assertEqual(get_stocks(["AAPL"]), [quote])


class TestStocksRoute(unittest.TestCase):
    """Tests for the /get-stocks Flask route."""

    def test_route_returns_quotes_as_json(self):
        """GET /get-stocks serves quotes through the Flask app."""
        from app import create_app

        fake = FakeRedis()
        quote = _quote_from_meta("AAPL", _meta())
        with (
            patch("app.REDIS_CLIENT", fake),
            patch.object(stocks, "REDIS_CLIENT", fake),
            patch.object(stocks, "_fetch_quote", return_value=quote),
        ):
            client = create_app().test_client()
            response = client.get("/get-stocks?symbols=AAPL")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["symbol"], "AAPL")
        self.assertEqual(data[0]["price"], 342.56)
        self.assertEqual(data[0]["as_of"], "2026-11-20T21:00:02+00:00")

    def test_route_without_symbols_serves_watchlist(self):
        """GET /get-stocks with no param serves the default watchlist."""
        from app import create_app

        def fake_fetch(symbol):
            """Return a quote carrying the requested symbol."""
            return _quote_from_meta(symbol, _meta(symbol=symbol, longName=f"{symbol} Inc."))

        fake = FakeRedis()
        with (
            patch("app.REDIS_CLIENT", fake),
            patch.object(stocks, "REDIS_CLIENT", fake),
            patch.object(stocks, "_fetch_quote", side_effect=fake_fetch),
        ):
            client = create_app().test_client()
            response = client.get("/get-stocks")
        self.assertEqual(response.status_code, 200)
        symbols = [item["symbol"] for item in response.get_json()]
        self.assertEqual(symbols, stocks.DEFAULT_SYMBOLS)


if __name__ == "__main__":
    unittest.main()
