"""Tests for app.stocks."""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from app import stocks
from app.stocks import (
    History,
    HistoryPoint,
    Quote,
    _fetch_history_nasdaq,
    _fetch_history_yahoo,
    _fetch_quote,
    _fetch_quote_nasdaq,
    _fill_day_range,
    _history_points_from_nasdaq,
    _history_points_from_yahoo,
    _parse_nasdaq_number,
    _quote_from_meta,
    _quote_from_nasdaq,
    clean_symbols,
    get_history,
    get_stocks,
    history_to_dict,
    quote_to_dict,
)


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


def _nasdaq_payload(symbol="AAPL", **overrides):
    """Build a Nasdaq quote info response with test values."""
    data = {
        "symbol": symbol,
        "companyName": "Apple Inc. Common Stock",
        "primaryData": {
            "lastSalePrice": "$342.56",
            "netChange": "-6.65",
            "percentageChange": "-1.90%",
            "lastTradeTimestamp": "Nov 20, 2026",
            "volume": "80,692,545",
        },
    }
    data.update(overrides)
    return {"data": data, "message": None, "status": {"rCode": 200}}


def _nasdaq_unknown_payload():
    """Build a Nasdaq response for a symbol that does not exist."""
    return {
        "data": None,
        "message": None,
        "status": {
            "rCode": 400,
            "bCodeMessage": [{"code": 1001, "errorMessage": "Symbol not exists."}],
        },
    }


def _http_error(code, message):
    """Build an HTTPError with the given status code."""
    return urllib.error.HTTPError("http://x", code, message, hdrs=None, fp=None)


def _json_body(payload):
    """Wrap a JSON payload as a urlopen response body."""
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class TestParseNasdaqNumber(unittest.TestCase):
    """Tests for _parse_nasdaq_number."""

    def test_dollar_and_commas_stripped(self):
        """A dollar string with commas parses to a float."""
        self.assertEqual(_parse_nasdaq_number("$1,234.56"), 1234.56)

    def test_percent_stripped(self):
        """A percent string parses to a plain float."""
        self.assertEqual(_parse_nasdaq_number("-1.90%"), -1.90)

    def test_na_and_none_become_none(self):
        """N/A and missing values parse to None."""
        self.assertIsNone(_parse_nasdaq_number("N/A"))
        self.assertIsNone(_parse_nasdaq_number(None))

    def test_number_passes_through(self):
        """A plain number passes through as a float."""
        self.assertEqual(_parse_nasdaq_number(42), 42.0)


class TestQuoteFromNasdaq(unittest.TestCase):
    """Tests for _quote_from_nasdaq."""

    def test_fields_map_and_name_cleaned(self):
        """Nasdaq fields map onto the quote and the name is cleaned."""
        quote = _quote_from_nasdaq("AAPL", _nasdaq_payload()["data"])
        self.assertEqual(quote.symbol, "AAPL")
        self.assertEqual(quote.name, "Apple Inc.")
        self.assertEqual(quote.price, 342.56)
        self.assertEqual(quote.previous_close, 349.21)
        self.assertEqual(quote.change, -6.65)
        self.assertEqual(quote.change_percent, -1.90)
        self.assertIsNone(quote.day_high)
        self.assertIsNone(quote.day_low)
        self.assertEqual(quote.volume, 80692545)
        self.assertEqual(quote.as_of.isoformat(), "2026-11-20T00:00:00+00:00")
        self.assertIsNone(quote.error)

    def test_class_share_name_cleaned(self):
        """A class-share suffix is stripped from the company name."""
        payload = _nasdaq_payload(companyName="Alphabet Inc. Class A Common Stock")
        quote = _quote_from_nasdaq("GOOGL", payload["data"])
        self.assertEqual(quote.name, "Alphabet Inc.")

    def test_missing_fields_become_none(self):
        """A bare Nasdaq object gives a quote with no values."""
        quote = _quote_from_nasdaq("AAPL", {"symbol": "AAPL"})
        self.assertIsNone(quote.name)
        self.assertIsNone(quote.price)
        self.assertIsNone(quote.as_of)


class TestFetchQuoteNasdaq(unittest.TestCase):
    """Tests for _fetch_quote_nasdaq with a mocked network."""

    def test_success(self):
        """A Nasdaq info response becomes a quote."""
        with patch("urllib.request.urlopen", return_value=_json_body(_nasdaq_payload())):
            quote = _fetch_quote_nasdaq("AAPL")
        self.assertEqual(quote.price, 342.56)
        self.assertIsNone(quote.error)

    def test_unknown_symbol_is_not_found(self):
        """A 'Symbol not exists' response becomes not_found."""
        with patch("urllib.request.urlopen", return_value=_json_body(_nasdaq_unknown_payload())):
            quote = _fetch_quote_nasdaq("ZZZZQQQ")
        self.assertEqual(quote.error, "not_found")
        self.assertIsNone(quote.price)

    def test_http_404_is_not_found(self):
        """An HTTP 404 becomes a not_found quote."""
        with patch("urllib.request.urlopen", side_effect=_http_error(404, "Not Found")):
            quote = _fetch_quote_nasdaq("ZZZZQQQ")
        self.assertEqual(quote.error, "not_found")

    def test_http_403_is_unavailable(self):
        """An HTTP 403 becomes an unavailable quote."""
        with patch("urllib.request.urlopen", side_effect=_http_error(403, "Forbidden")):
            quote = _fetch_quote_nasdaq("AAPL")
        self.assertEqual(quote.error, "unavailable")


class TestFetchQuoteFallback(unittest.TestCase):
    """Tests for the Yahoo-first, Nasdaq-fallback order in _fetch_quote."""

    def test_yahoo_429_falls_back_to_nasdaq(self):
        """A blocked Yahoo fetch is rescued by the Nasdaq fallback."""
        calls = [_http_error(429, "Too Many Requests"), _json_body(_nasdaq_payload())]
        with patch("urllib.request.urlopen", side_effect=calls):
            quote = _fetch_quote("AAPL")
        self.assertEqual(quote.price, 342.56)
        self.assertEqual(quote.name, "Apple Inc.")
        self.assertIsNone(quote.error)

    def test_yahoo_404_does_not_fall_back(self):
        """A Yahoo not_found is returned without trying Nasdaq."""
        with patch("urllib.request.urlopen", side_effect=_http_error(404, "Not Found")) as mock:
            quote = _fetch_quote("ZZZZQQQ")
        self.assertEqual(quote.error, "not_found")
        mock.assert_called_once()

    def test_both_sources_failing_is_unavailable(self):
        """When Yahoo and Nasdaq both fail, the quote is unavailable."""
        calls = [_http_error(429, "Too Many Requests"), _http_error(403, "Forbidden")]
        with patch("urllib.request.urlopen", side_effect=calls):
            quote = _fetch_quote("AAPL")
        self.assertEqual(quote.error, "unavailable")
        self.assertIsNone(quote.price)

    def test_yahoo_down_nasdaq_unknown_is_not_found(self):
        """A down Yahoo plus an unknown Nasdaq symbol is not_found."""
        calls = [_http_error(429, "Too Many Requests"), _json_body(_nasdaq_unknown_payload())]
        with patch("urllib.request.urlopen", side_effect=calls):
            quote = _fetch_quote("ZZZZQQQ")
        self.assertEqual(quote.error, "not_found")


if __name__ == "__main__":
    unittest.main()


def _day_timestamp(day):
    """Epoch seconds for midnight UTC on a November 2026 day."""
    from datetime import datetime, timezone

    return int(datetime(2026, 11, day, tzinfo=timezone.utc).timestamp())


def _yahoo_history_payload():
    """Build a Yahoo chart response with 3 daily candles (one null)."""
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "AAPL"},
                    "timestamp": [_day_timestamp(18), _day_timestamp(19), _day_timestamp(20)],
                    "indicators": {
                        "quote": [
                            {
                                "close": [340.0, None, 342.56],
                                "high": [344.0, 345.0, 354.3],
                                "low": [338.0, 339.0, 340.56],
                                "open": [342.0, 343.0, 350.0],
                                "volume": [100, 200, 300],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def _nasdaq_chart_payload(points=3):
    """Build a Nasdaq chart response with minute bars."""
    base = 1795147200000  # Nov 20, 2026 04:00 UTC in ms
    chart = [
        {
            "x": base + i * 60000,
            "y": 350.0 + i,
            "z": {"dateTime": "4:00 AM ET", "value": str(350.0 + i)},
        }
        for i in range(points)
    ]
    return {"data": {"symbol": "AAPL", "chart": chart}, "message": None, "status": {"rCode": 200}}


class TestHistoryPointsFromYahoo(unittest.TestCase):
    """Tests for _history_points_from_yahoo."""

    def test_closes_highs_lows_parsed_and_null_skipped(self):
        """Daily candles parse with OHLC; a null close is skipped."""
        points = _history_points_from_yahoo(_yahoo_history_payload()["chart"]["result"][0])
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].date, "2026-11-18")
        self.assertEqual(points[0].close, 340.0)
        self.assertEqual(points[0].high, 344.0)
        self.assertEqual(points[0].low, 338.0)
        self.assertEqual(points[1].date, "2026-11-20")
        self.assertEqual(points[1].close, 342.56)
        self.assertEqual(points[1].high, 354.3)
        self.assertEqual(points[1].low, 340.56)


class TestFetchHistoryYahoo(unittest.TestCase):
    """Tests for _fetch_history_yahoo with a mocked network."""

    def test_success(self):
        """A chart response becomes a month history."""
        with patch("urllib.request.urlopen", return_value=_json_body(_yahoo_history_payload())):
            history = _fetch_history_yahoo("AAPL")
        self.assertEqual(history.symbol, "AAPL")
        self.assertEqual(history.source, "yahoo")
        self.assertEqual(history.label, "Past month")
        self.assertEqual(len(history.points), 2)
        self.assertEqual(history.day_high, 354.3)
        self.assertEqual(history.day_low, 340.56)
        self.assertIsNone(history.error)

    def test_chart_error_is_not_found(self):
        """A chart error becomes a not_found history."""
        payload = {"chart": {"result": None, "error": {"code": "Not Found"}}}
        with patch("urllib.request.urlopen", return_value=_json_body(payload)):
            history = _fetch_history_yahoo("ZZZZQQQ")
        self.assertEqual(history.error, "not_found")
        self.assertEqual(history.points, [])

    def test_http_429_is_unavailable(self):
        """An HTTP 429 becomes an unavailable history."""
        with patch("urllib.request.urlopen", side_effect=_http_error(429, "Too Many Requests")):
            history = _fetch_history_yahoo("AAPL")
        self.assertEqual(history.error, "unavailable")


class TestHistoryPointsFromNasdaq(unittest.TestCase):
    """Tests for _history_points_from_nasdaq."""

    def test_points_parsed(self):
        """Minute bars parse to dated points."""
        points = _history_points_from_nasdaq(_nasdaq_chart_payload(3)["data"]["chart"])
        self.assertEqual(len(points), 3)
        self.assertEqual(points[0].close, 350.0)
        self.assertTrue(points[0].date.startswith("2026-11-20T04:00"))
        self.assertIsNone(points[0].high)
        self.assertIsNone(points[0].low)

    def test_many_points_downsampled_keeping_ends(self):
        """Hundreds of bars downsample to at most 121, keeping the ends."""
        points = _history_points_from_nasdaq(_nasdaq_chart_payload(300)["data"]["chart"])
        self.assertLessEqual(len(points), 121)
        self.assertEqual(points[0].close, 350.0)
        self.assertEqual(points[-1].close, 649.0)


class TestFetchHistoryNasdaq(unittest.TestCase):
    """Tests for _fetch_history_nasdaq with a mocked network."""

    def test_success(self):
        """A Nasdaq chart response becomes a session history."""
        with patch("urllib.request.urlopen", return_value=_json_body(_nasdaq_chart_payload())):
            history = _fetch_history_nasdaq("AAPL")
        self.assertEqual(history.source, "nasdaq")
        self.assertEqual(history.label, "Today's session")
        self.assertEqual(len(history.points), 3)
        self.assertIsNone(history.error)

    def test_day_range_is_session_max_min(self):
        """The day range is the session's traded max/min."""
        with patch("urllib.request.urlopen", return_value=_json_body(_nasdaq_chart_payload())):
            history = _fetch_history_nasdaq("AAPL")
        self.assertEqual(history.day_high, 352.0)
        self.assertEqual(history.day_low, 350.0)

    def test_unknown_symbol_is_not_found(self):
        """A 'Symbol not exists' response becomes not_found."""
        with patch("urllib.request.urlopen", return_value=_json_body(_nasdaq_unknown_payload())):
            history = _fetch_history_nasdaq("ZZZZQQQ")
        self.assertEqual(history.error, "not_found")


class TestGetHistory(unittest.TestCase):
    """Tests for get_history caching and fallback order."""

    def test_yahoo_429_falls_back_to_nasdaq(self):
        """A blocked Yahoo history is rescued by Nasdaq."""
        fake = FakeRedis()
        calls = [_http_error(429, "Too Many Requests"), _json_body(_nasdaq_chart_payload())]
        with patch.object(stocks, "REDIS_CLIENT", fake):
            with patch("urllib.request.urlopen", side_effect=calls):
                history = get_history("AAPL")
        self.assertEqual(history.source, "nasdaq")
        self.assertEqual(len(history.points), 3)
        self.assertIsNone(history.error)

    def test_yahoo_not_found_does_not_fall_back(self):
        """A Yahoo not_found is returned without trying Nasdaq."""
        fake = FakeRedis()
        payload = {"chart": {"result": None, "error": {"code": "Not Found"}}}
        with patch.object(stocks, "REDIS_CLIENT", fake):
            with patch("urllib.request.urlopen", return_value=_json_body(payload)) as mock:
                history = get_history("ZZZZQQQ")
        self.assertEqual(history.error, "not_found")
        mock.assert_called_once()

    def test_both_sources_failing_is_unavailable(self):
        """When Yahoo and Nasdaq both fail, the history is unavailable."""
        fake = FakeRedis()
        calls = [_http_error(429, "Too Many Requests"), _http_error(403, "Forbidden")]
        with patch.object(stocks, "REDIS_CLIENT", fake):
            with patch("urllib.request.urlopen", side_effect=calls):
                history = get_history("AAPL")
        self.assertEqual(history.error, "unavailable")
        self.assertEqual(history.points, [])

    def test_cache_hit_skips_fetch(self):
        """A cached history is returned without fetching."""
        fake = FakeRedis()
        history = History(
            "AAPL", "yahoo", "Past month", [HistoryPoint("2026-11-20", 342.56, 354.3, 340.56)]
        )
        fake.save_entry("history:AAPL", history_to_dict(history), expiration=900)
        with patch.object(stocks, "REDIS_CLIENT", fake):
            with patch.object(
                stocks, "_fetch_history_yahoo", side_effect=AssertionError("should not fetch")
            ):
                result = get_history("AAPL")
        self.assertEqual(result, history)


class TestFillDayRange(unittest.TestCase):
    """Tests for _fill_day_range."""

    def test_nasdaq_quote_gets_range_from_last_candle(self):
        """A quote without a day range takes the last candle's high/low."""
        quote = _quote_from_nasdaq("AAPL", _nasdaq_payload()["data"])
        self.assertIsNone(quote.day_high)
        history = History(
            "AAPL",
            "yahoo",
            "Past month",
            [
                HistoryPoint("2026-11-19", 340.0, 344.0, 338.0),
                HistoryPoint("2026-11-20", 342.56, 354.3, 340.56),
            ],
            day_high=354.3,
            day_low=340.56,
        )
        with patch.object(stocks, "get_history", return_value=history):
            _fill_day_range([quote])
        self.assertEqual(quote.day_high, 354.3)
        self.assertEqual(quote.day_low, 340.56)

    def test_nasdaq_session_range_fills_from_session_max_min(self):
        """A Nasdaq session history fills the range from its max/min."""
        quote = _quote_from_nasdaq("AAPL", _nasdaq_payload()["data"])
        history = History(
            "AAPL",
            "nasdaq",
            "Today's session",
            [HistoryPoint("2026-11-20T04:00:00+00:00", 350.0)],
            day_high=352.0,
            day_low=350.0,
        )
        with patch.object(stocks, "get_history", return_value=history):
            _fill_day_range([quote])
        self.assertEqual(quote.day_high, 352.0)
        self.assertEqual(quote.day_low, 350.0)

    def test_unavailable_history_leaves_dashes(self):
        """When the history is unavailable, the day range stays empty."""
        quote = _quote_from_nasdaq("AAPL", _nasdaq_payload()["data"])
        with patch.object(
            stocks, "get_history", return_value=History("AAPL", None, "", [], "unavailable")
        ):
            _fill_day_range([quote])
        self.assertIsNone(quote.day_high)
        self.assertIsNone(quote.day_low)

    def test_quote_with_range_is_not_refetched(self):
        """A quote that already has a day range triggers no history fetch."""
        quote = _quote_from_meta("AAPL", _meta())
        self.assertIsNotNone(quote.day_high)
        with patch.object(
            stocks, "get_history", side_effect=AssertionError("should not fetch")
        ):
            _fill_day_range([quote])
        self.assertEqual(quote.day_high, 354.3)


class TestGetStocksFillsDayRange(unittest.TestCase):
    """Tests that get_stocks fills a Nasdaq quote's day range."""

    def test_nasdaq_quote_day_range_filled(self):
        """A watchlist quote from Nasdaq gets its day range filled."""
        fake = FakeRedis()
        quote = _quote_from_nasdaq("AAPL", _nasdaq_payload()["data"])
        history = History(
            "AAPL",
            "yahoo",
            "Past month",
            [HistoryPoint("2026-11-20", 342.56, 354.3, 340.56)],
            day_high=354.3,
            day_low=340.56,
        )
        with patch.object(stocks, "REDIS_CLIENT", fake):
            with patch.object(stocks, "_fetch_quote", return_value=quote):
                with patch.object(stocks, "get_history", return_value=history):
                    result = get_stocks(["AAPL"])
        self.assertEqual(result[0].day_high, 354.3)
        self.assertEqual(result[0].day_low, 340.56)


class TestHistoryRoute(unittest.TestCase):
    """Tests for the /get-history Flask route."""

    def test_route_returns_history_as_json(self):
        """GET /get-history serves points through the Flask app."""
        from app import create_app

        fake = FakeRedis()
        history = History(
            "AAPL",
            "yahoo",
            "Past month",
            [HistoryPoint("2026-11-20", 342.56, 354.3, 340.56)],
            day_high=354.3,
            day_low=340.56,
        )
        with (
            patch("app.REDIS_CLIENT", fake),
            patch.object(stocks, "REDIS_CLIENT", fake),
            patch.object(stocks, "_fetch_history_yahoo", return_value=history),
        ):
            client = create_app().test_client()
            response = client.get("/get-history?symbol=AAPL")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["symbol"], "AAPL")
        self.assertEqual(data["source"], "yahoo")
        self.assertEqual(data["label"], "Past month")
        self.assertEqual(data["points"][0]["close"], 342.56)
        self.assertEqual(data["points"][0]["high"], 354.3)
        self.assertEqual(data["day_high"], 354.3)
        self.assertEqual(data["day_low"], 340.56)

    def test_route_without_symbol_is_400(self):
        """GET /get-history with no symbol is a bad request."""
        from app import create_app

        fake = FakeRedis()
        with (
            patch("app.REDIS_CLIENT", fake),
            patch.object(stocks, "REDIS_CLIENT", fake),
        ):
            client = create_app().test_client()
            response = client.get("/get-history")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "not_found")
