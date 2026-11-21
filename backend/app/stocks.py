"""Module for retrieving stock quotes."""

import json
import logging
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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
    _save_cached(symbols, quotes)
    return quotes
