"""Module for retrieving stock quotes."""

import json
import logging
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.utils.redis import REDIS_CLIENT

logger = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
NASDAQ_INFO_URL = "https://api.nasdaq.com/api/quote/{symbol}/info?assetclass=stocks"

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_CACHE_TTL_SECONDS = 120
_MAX_SYMBOLS = 20

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "NFLX", "AMD"]

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")


@dataclass
class Quote:
    """Dataclass for a stock quote."""

    symbol: str
    name: Optional[str]
    price: Optional[float]
    previous_close: Optional[float]
    change: Optional[float]
    change_percent: Optional[float]
    day_high: Optional[float]
    day_low: Optional[float]
    volume: Optional[int]
    as_of: Optional[datetime]
    error: Optional[str] = None


def clean_symbols(raw: Optional[str]) -> list[str]:
    """Clean a comma-separated symbols string into valid uppercase tickers.

    Only letters, digits, dots, and dashes are kept; anything else is dropped.
    Symbols are deduplicated in order and capped at _MAX_SYMBOLS.
    """
    if not raw:
        return []
    cleaned: list[str] = []
    for part in raw.split(","):
        symbol = part.strip().upper()
        if symbol and _SYMBOL_RE.match(symbol) and symbol not in cleaned:
            cleaned.append(symbol)
    return cleaned[:_MAX_SYMBOLS]


def _cache_key(symbols: list[str]) -> str:
    """Build the Redis cache key for a set of symbols."""
    return "stocks:" + ",".join(symbols)


def quote_to_dict(quote: Quote) -> dict[str, Any]:
    """Convert a quote to a JSON friendly dict."""
    data = asdict(quote)
    data["as_of"] = quote.as_of.isoformat() if quote.as_of else None
    return data


def _quote_from_dict(data: dict[str, Any]) -> Quote:
    """Rebuild a quote from a cached dict."""
    as_of = data.get("as_of")
    return Quote(
        symbol=data["symbol"],
        name=data.get("name"),
        price=data.get("price"),
        previous_close=data.get("previous_close"),
        change=data.get("change"),
        change_percent=data.get("change_percent"),
        day_high=data.get("day_high"),
        day_low=data.get("day_low"),
        volume=data.get("volume"),
        as_of=datetime.fromisoformat(as_of) if as_of else None,
        error=data.get("error"),
    )


def _quote_from_meta(symbol: str, meta: dict[str, Any]) -> Quote:
    """Format a Yahoo Finance chart meta object into a Quote."""
    price = meta.get("regularMarketPrice")
    previous_close = meta.get("chartPreviousClose")
    change = None
    if price is not None and previous_close is not None:
        change = round(price - previous_close, 2)
    change_percent = meta.get("regularMarketChangePercent")
    if change_percent is None and change is not None and previous_close:
        change_percent = round(change / previous_close * 100, 2)
    as_of = meta.get("regularMarketTime")
    return Quote(
        symbol=symbol,
        name=meta.get("longName") or meta.get("shortName"),
        price=price,
        previous_close=previous_close,
        change=change,
        change_percent=change_percent,
        day_high=meta.get("regularMarketDayHigh"),
        day_low=meta.get("regularMarketDayLow"),
        volume=meta.get("regularMarketVolume"),
        as_of=datetime.fromtimestamp(as_of, tz=timezone.utc) if as_of else None,
    )


def _fetch_quote_yahoo(symbol: str) -> Quote:
    """Fetch one quote from the Yahoo Finance chart API.

    No API key is needed. A browser User-Agent is required; without one
    Yahoo answers 429. A delisted or unknown symbol returns error
    "not_found"; any other failure returns error "unavailable". Failures
    are logged (status code or error type) so the server log shows the
    real cause instead of just "unavailable".
    """
    url = YAHOO_CHART_URL.format(symbol=symbol)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.warning("Yahoo fetch failed for %s: HTTP %s", symbol, e.code)
        error = "not_found" if e.code == 404 else "unavailable"
        return Quote(symbol, None, None, None, None, None, None, None, None, None, error)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        logger.warning("Yahoo fetch failed for %s: %s", symbol, type(e).__name__)
        return Quote(symbol, None, None, None, None, None, None, None, None, None, "unavailable")
    chart = payload.get("chart", {})
    if chart.get("error") is not None:
        return Quote(symbol, None, None, None, None, None, None, None, None, None, "not_found")
    result = chart.get("result") or []
    if not result:
        return Quote(symbol, None, None, None, None, None, None, None, None, None, "not_found")
    return _quote_from_meta(symbol, result[0].get("meta", {}))


def _parse_nasdaq_number(value: Any) -> Optional[float]:
    """Parse a Nasdaq number string like "$342.56", "-1.90%", or "N/A"."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
    if text in ("", "N/A", "NA"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _quote_from_nasdaq(symbol: str, data: dict[str, Any]) -> Quote:
    """Format a Nasdaq quote info object into a Quote.

    Nasdaq gives day high/low only as "NA", so those stay None. The
    last trade date is a plain date ("Nov 20, 2026"), used as the as-of
    time at midnight UTC.
    """
    primary = data.get("primaryData") or {}
    price = _parse_nasdaq_number(primary.get("lastSalePrice"))
    change = _parse_nasdaq_number(primary.get("netChange"))
    change_percent = _parse_nasdaq_number(primary.get("percentageChange"))
    previous_close = None
    if price is not None and change is not None:
        previous_close = round(price - change, 2)
    volume = _parse_nasdaq_number(primary.get("volume"))
    name = data.get("companyName")
    if name:
        name = re.sub(r"\s+(Class [A-Z]\s+)?Common Stock$", "", name)
    as_of = None
    timestamp = primary.get("lastTradeTimestamp")
    if timestamp:
        try:
            as_of = datetime.strptime(timestamp, "%b %d, %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            as_of = None
    return Quote(
        symbol=symbol,
        name=name,
        price=price,
        previous_close=previous_close,
        change=change,
        change_percent=change_percent,
        day_high=None,
        day_low=None,
        volume=int(volume) if volume is not None else None,
        as_of=as_of,
    )


def _fetch_quote_nasdaq(symbol: str) -> Quote:
    """Fetch one quote from the Nasdaq quote API (fallback source).

    No API key is needed. An unknown symbol returns error "not_found"
    (the API answers 200 with data null and "Symbol not exists.");
    any other failure returns error "unavailable".
    """
    url = NASDAQ_INFO_URL.format(symbol=symbol)
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.warning("Nasdaq fetch failed for %s: HTTP %s", symbol, e.code)
        error = "not_found" if e.code == 404 else "unavailable"
        return Quote(symbol, None, None, None, None, None, None, None, None, None, error)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        logger.warning("Nasdaq fetch failed for %s: %s", symbol, type(e).__name__)
        return Quote(symbol, None, None, None, None, None, None, None, None, None, "unavailable")
    data = payload.get("data")
    if not data:
        message = json.dumps(payload.get("status") or {})
        error = "not_found" if "not exists" in message.lower() else "unavailable"
        return Quote(symbol, None, None, None, None, None, None, None, None, None, error)
    return _quote_from_nasdaq(symbol, data)


def _fetch_quote(symbol: str) -> Quote:
    """Fetch one quote, Yahoo Finance first, Nasdaq as the fallback.

    Yahoo answers first. Only when Yahoo fails with "unavailable"
    (blocked, rate-limited, timeout, or any other transport failure)
    is Nasdaq tried, so one blocked source does not blank the page.
    A Yahoo "not_found" means the symbol is unknown and is returned
    as-is without a fallback attempt.
    """
    quote = _fetch_quote_yahoo(symbol)
    if quote.error == "unavailable":
        return _fetch_quote_nasdaq(symbol)
    return quote


def _load_cached(symbols: list[str]) -> Optional[list[Quote]]:
    """Load quotes from the Redis cache, or None on a miss or cache error."""
    try:
        cached = REDIS_CLIENT.get_entry(_cache_key(symbols))
    except Exception:
        return None
    if cached is None:
        return None
    try:
        return [_quote_from_dict(item) for item in cached]
    except Exception:
        return None


def _save_cached(symbols: list[str], quotes: list[Quote]) -> None:
    """Save quotes to the Redis cache; cache errors are ignored."""
    try:
        REDIS_CLIENT.save_entry(
            _cache_key(symbols),
            [quote_to_dict(quote) for quote in quotes],
            expiration=_CACHE_TTL_SECONDS,
        )
    except Exception:
        pass


def _fill_day_range(quotes: list[Quote]) -> list[Quote]:
    """Fill missing day high/low from the most recent daily candle.

    Quotes that came from Nasdaq carry no day range. For those, the
    high/low of the most recent trading day's candle comes from the
    Yahoo history (the last daily candle). If that history is
    unavailable, the values stay None and the page shows dashes —
    never invented.
    """
    missing = [q for q in quotes if q.day_high is None or q.day_low is None]
    if not missing:
        return quotes

    def _fill(quote: Quote) -> Quote:
        history = get_history(quote.symbol)
        if history.error or (history.day_high is None and history.day_low is None):
            return quote
        if quote.day_high is None:
            quote.day_high = history.day_high
        if quote.day_low is None:
            quote.day_low = history.day_low
        return quote

    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(_fill, missing))
    return quotes


def get_stocks(symbols: Optional[list[str]] = None) -> list[Quote]:
    """Get stock quotes for the given symbols, or the default watchlist.

    Results are cached in Redis for a few minutes. If the cache is
    unavailable, quotes are fetched live instead.
    """
    if symbols is None:
        symbols = list(DEFAULT_SYMBOLS)
    if not symbols:
        return []
    cached = _load_cached(symbols)
    if cached is not None:
        return cached
    with ThreadPoolExecutor(max_workers=5) as executor:
        quotes = list(executor.map(_fetch_quote, symbols))
    quotes = _fill_day_range(quotes)
    _save_cached(symbols, quotes)
    return quotes


YAHOO_HISTORY_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d"
)
NASDAQ_CHART_URL = "https://api.nasdaq.com/api/quote/{symbol}/chart?assetclass=stocks"
NASDAQ_HISTORY_URL = (
    "https://api.nasdaq.com/api/quote/{symbol}/historical"
    "?assetclass=stocks&fromdate={fromdate}&todate={todate}&limit=31"
)
_HISTORY_CACHE_TTL_SECONDS = 900
# The single-session fallback is a last resort (it answers a different
# question than the month view), so it is cached only briefly — one
# Yahoo hiccup must not pin the chart to one session for 15 minutes.
_HISTORY_FALLBACK_CACHE_TTL_SECONDS = 120
_MAX_HISTORY_POINTS = 120


@dataclass
class HistoryPoint:
    """One price point in a price history series."""

    date: str  # ISO date, e.g. "2026-11-20" (or a datetime for intraday)
    close: float
    high: Optional[float] = None  # day's candle high (daily bars only)
    low: Optional[float] = None  # day's candle low (daily bars only)


@dataclass
class History:
    """A price history series for one symbol."""

    symbol: str
    source: Optional[str]  # "yahoo" | "nasdaq" | None
    label: str  # human range label, e.g. "Past month"
    points: list[HistoryPoint]
    error: Optional[str] = None
    # Most recent trading day's range. For Yahoo this is the last daily
    # candle's high/low; for Nasdaq it is the session's traded max/min
    # (both real data, never invented).
    day_high: Optional[float] = None
    day_low: Optional[float] = None


def history_to_dict(history: History) -> dict[str, Any]:
    """Convert a history to a JSON friendly dict."""
    return {
        "symbol": history.symbol,
        "source": history.source,
        "label": history.label,
        "points": [asdict(point) for point in history.points],
        "error": history.error,
        "day_high": history.day_high,
        "day_low": history.day_low,
    }


def _history_from_dict(data: dict[str, Any]) -> History:
    """Rebuild a history from a cached dict."""
    return History(
        symbol=data["symbol"],
        source=data.get("source"),
        label=data.get("label", ""),
        points=[
            HistoryPoint(p["date"], p["close"], p.get("high"), p.get("low"))
            for p in data.get("points", [])
        ],
        error=data.get("error"),
        day_high=data.get("day_high"),
        day_low=data.get("day_low"),
    )


def _history_points_from_yahoo(result: dict[str, Any]) -> list[HistoryPoint]:
    """Parse Yahoo chart timestamps + OHLC into history points.

    Null closes (market holidays, partial days) are skipped. The high
    and low of each daily candle are kept so the most recent trading
    day's range can fill in a quote that has none.
    """
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators", {}).get("quote") or []
    quote = indicators[0] if indicators else {}
    closes = quote.get("close") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    points: list[HistoryPoint] = []
    for i, (timestamp, close) in enumerate(zip(timestamps, closes)):
        if close is None:
            continue
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
        high = highs[i] if i < len(highs) else None
        low = lows[i] if i < len(lows) else None
        points.append(
            HistoryPoint(
                date=date,
                close=float(close),
                high=float(high) if high is not None else None,
                low=float(low) if low is not None else None,
            )
        )
    return points


def _fetch_history_yahoo(symbol: str) -> History:
    """Fetch a month of daily closes from the Yahoo Finance chart API.

    No API key is needed; a browser User-Agent is required. An unknown
    symbol returns error "not_found"; any other failure returns error
    "unavailable".
    """
    url = YAHOO_HISTORY_URL.format(symbol=symbol)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.warning("Yahoo history fetch failed for %s: HTTP %s", symbol, e.code)
        error = "not_found" if e.code == 404 else "unavailable"
        return History(symbol, None, "", [], error)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        logger.warning("Yahoo history fetch failed for %s: %s", symbol, type(e).__name__)
        return History(symbol, None, "", [], "unavailable")
    chart = payload.get("chart", {})
    if chart.get("error") is not None:
        return History(symbol, None, "", [], "not_found")
    result = chart.get("result") or []
    if not result:
        return History(symbol, None, "", [], "not_found")
    points = _history_points_from_yahoo(result[0])
    if not points:
        return History(symbol, None, "", [], "not_found")
    last = points[-1]
    return History(
        symbol, "yahoo", "Past month", points, day_high=last.high, day_low=last.low
    )


def _history_points_from_nasdaq(chart: list[dict[str, Any]]) -> list[HistoryPoint]:
    """Parse Nasdaq intraday chart points into history points.

    Nasdaq returns minute bars for the current session; points are
    downsampled to at most _MAX_HISTORY_POINTS so the chart stays
    readable, keeping the first and last point.
    """
    raw: list[HistoryPoint] = []
    for item in chart or []:
        try:
            timestamp = int(item.get("x", 0)) // 1000
            close = float(item.get("y"))
        except (TypeError, ValueError):
            continue
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        raw.append(HistoryPoint(date=date, close=close))
    if len(raw) <= _MAX_HISTORY_POINTS:
        return raw
    step = len(raw) / _MAX_HISTORY_POINTS
    sampled = [raw[int(i * step)] for i in range(_MAX_HISTORY_POINTS)]
    if sampled[-1] is not raw[-1]:
        sampled.append(raw[-1])
    return sampled


def _fetch_history_nasdaq(symbol: str) -> History:
    """Fetch the current session's price points from the Nasdaq chart API.

    No API key is needed. An unknown symbol (data null) returns error
    "not_found"; any other failure returns error "unavailable".
    """
    url = NASDAQ_CHART_URL.format(symbol=symbol)
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.warning("Nasdaq history fetch failed for %s: HTTP %s", symbol, e.code)
        error = "not_found" if e.code == 404 else "unavailable"
        return History(symbol, None, "", [], error)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        logger.warning("Nasdaq history fetch failed for %s: %s", symbol, type(e).__name__)
        return History(symbol, None, "", [], "unavailable")
    data = payload.get("data") or {}
    chart = data.get("chart") or []
    if not chart:
        message = json.dumps(payload.get("status") or {})
        error = "not_found" if "not exists" in message.lower() else "unavailable"
        return History(symbol, None, "", [], error)
    points = _history_points_from_nasdaq(chart)
    if not points:
        return History(symbol, None, "", [], "unavailable")
    closes = [point.close for point in points]
    return History(
        symbol,
        "nasdaq",
        "Today's session",
        points,
        day_high=max(closes),
        day_low=min(closes),
    )


def _history_points_from_nasdaq_daily(rows: list[dict[str, Any]]) -> list[HistoryPoint]:
    """Parse Nasdaq historical rows (newest first) into daily points.

    Rows carry "MM/DD/YYYY" dates and "$1,234.56" numbers. The result
    is flipped to oldest-first, the order the chart is drawn in.
    """
    points: list[HistoryPoint] = []
    for row in rows or []:
        try:
            date = datetime.strptime(row.get("date", ""), "%m/%d/%Y").date().isoformat()
        except (TypeError, ValueError):
            continue
        close = _parse_nasdaq_number(row.get("close"))
        if close is None:
            continue
        points.append(
            HistoryPoint(
                date=date,
                close=close,
                high=_parse_nasdaq_number(row.get("high")),
                low=_parse_nasdaq_number(row.get("low")),
            )
        )
    return list(reversed(points))


def _fetch_history_nasdaq_daily(symbol: str) -> History:
    """Fetch a month of daily closes from the Nasdaq historical API.

    The middle fallback: Yahoo's chart API frequently rate-limits
    datacenter IPs (it failed persistently from Render while the
    quote endpoint on the same host worked), which used to drop the
    chart straight to the single-session view. Nasdaq's historical
    endpoint serves the same month of daily bars from a host this
    app already reaches. No API key is needed.
    """
    today = datetime.now(timezone.utc).date()
    url = NASDAQ_HISTORY_URL.format(
        symbol=symbol,
        fromdate=(today - timedelta(days=45)).isoformat(),
        todate=today.isoformat(),
    )
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.warning("Nasdaq daily history fetch failed for %s: HTTP %s", symbol, e.code)
        error = "not_found" if e.code == 404 else "unavailable"
        return History(symbol, None, "", [], error)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        logger.warning(
            "Nasdaq daily history fetch failed for %s: %s", symbol, type(e).__name__
        )
        return History(symbol, None, "", [], "unavailable")
    data = payload.get("data") or {}
    rows = (data.get("tradesTable") or {}).get("rows") or []
    if not rows:
        message = json.dumps(payload.get("status") or {})
        error = "not_found" if "not exists" in message.lower() else "unavailable"
        return History(symbol, None, "", [], error)
    points = _history_points_from_nasdaq_daily(rows)
    if not points:
        return History(symbol, None, "", [], "unavailable")
    last = points[-1]
    return History(
        symbol, "nasdaq", "Past month", points, day_high=last.high, day_low=last.low
    )


def _history_cache_key(symbol: str) -> str:
    """Build the Redis cache key for a symbol's history."""
    return "history:" + symbol


def get_history(symbol: str) -> History:
    """Get a price history for one symbol: a month of daily closes.

    Yahoo first; when Yahoo is "unavailable" (its chart API often
    rate-limits datacenter IPs), Nasdaq's historical endpoint serves
    the same month of daily bars; the Nasdaq single-session chart is
    the last resort. A Yahoo "not_found" means the symbol is unknown
    and is returned as-is without a fallback attempt. Month views are
    cached for 15 minutes; the session fallback for only 2, so it
    never sticks around after the daily sources recover.
    """
    symbol = symbol.upper()
    cache_key = _history_cache_key(symbol)
    try:
        cached = REDIS_CLIENT.get_entry(cache_key)
    except Exception:
        cached = None
    if cached is not None:
        try:
            return _history_from_dict(cached)
        except Exception:
            pass
    history = _fetch_history_yahoo(symbol)
    if history.error == "unavailable":
        history = _fetch_history_nasdaq_daily(symbol)
    if history.error == "unavailable":
        history = _fetch_history_nasdaq(symbol)
    ttl = (
        _HISTORY_FALLBACK_CACHE_TTL_SECONDS
        if history.label == "Today's session"
        else _HISTORY_CACHE_TTL_SECONDS
    )
    try:
        REDIS_CLIENT.save_entry(cache_key, history_to_dict(history), expiration=ttl)
    except Exception:
        pass
    return history
