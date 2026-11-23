"""Live news fetching for the newsfeed.

The bundled dataset (backend/resources/dataset) is a fixed set of
2018 course articles: on its own the feed can never change, which is
why the site showed the same articles every day. This module pulls
current headlines from public RSS feeds (no API key needed), maps
them into the exact record shape the dataset uses, and stores them
in Redis under the same "all_articles" key the feed already reads.

Refresh policy: a background thread refreshes shortly after startup
and then every REFRESH_MINUTES. If every feed fails (offline, a feed
is down), whatever is already stored stays — the site never goes
empty because a fetch failed.
"""

import html
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# (author label, feed URL). All four verified live and current.
FEEDS = [
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("CNBC", "https://www.cnbc.com/id/19854910/device/rss/rss.html"),
    ("BBC News", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("BBC News", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
]

MAX_ARTICLES = 60
REFRESH_MINUTES = 30
FETCH_TIMEOUT_SECONDS = 15
USER_AGENT = "Mozilla/5.0 (compatible; TechLabTimes/1.0)"

_NS = {
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

_TAG_RE = re.compile(r"<[^>]+>")
_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')
_WS_RE = re.compile(r"\s+")
_OG_IMAGE_RE = re.compile(r'og:image"[^>]*?content="([^"]+)"')
_PAGE_READ_LIMIT = 262144  # og:image lives in <head>; no need for the full page


def _clean_text(raw: str) -> str:
    """Strip HTML from an RSS description into plain article text."""
    if not raw:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", raw))).strip()


def _item_image(item: ET.Element, description: str) -> str:
    """Best image URL for an RSS item, or "" when the feed has none."""
    for content in item.findall("media:content", _NS):
        url = content.get("url") or ""
        if url and (content.get("medium") == "image" or "image" in (content.get("type") or "")):
            return url
    thumbnails = item.findall("media:thumbnail", _NS)
    if thumbnails:
        return thumbnails[-1].get("url") or ""
    for enclosure in item.findall("enclosure"):
        if "image" in (enclosure.get("type") or "") and enclosure.get("url"):
            return enclosure.get("url")
    match = _IMG_RE.search(description or "")
    return match.group(1) if match else ""


def _item_date(item: ET.Element) -> datetime:
    raw = item.findtext("pubDate") or ""
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    return datetime.now(timezone.utc)


def parse_feed(xml_bytes: bytes, source: str) -> list[dict]:
    """Parse one RSS document into dataset-shaped article records."""
    root = ET.fromstring(xml_bytes)
    records = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if not title or not url:
            continue
        description = item.findtext("description") or ""
        author = (
            item.findtext("dc:creator", default="", namespaces=_NS) or ""
        ).strip() or source
        records.append(
            {
                "author": author,
                "title": html.unescape(title),
                "text": _clean_text(description),
                "published": _item_date(item).isoformat(),
                "url": url,
                "thread": {"main_image": _item_image(item, description)},
            }
        )
    return records


def extract_og_image(page_html: str) -> str:
    """The article page's og:image URL, or "" when it has none."""
    match = _OG_IMAGE_RE.search(page_html or "")
    return html.unescape(match.group(1)) if match else ""


def _fetch_og_image(article_url: str) -> str:
    """Fetch an article page just far enough to read its og:image."""
    try:
        request = urllib.request.Request(
            article_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            head = response.read(_PAGE_READ_LIMIT).decode("utf-8", errors="replace")
        return extract_og_image(head)
    except Exception:
        return ""


def _backfill_images(articles: list[dict]) -> None:
    """Fill missing images from the articles' own pages.

    CNBC's RSS carries no images at all (BBC's does), which left most
    cards showing the placeholder. Each article page names its image
    in og:image, so fetch those — concurrently, and only for the
    records that need one.
    """
    missing = [a for a in articles if not a["thread"]["main_image"]]
    if not missing:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        for article, image_url in zip(
            missing, pool.map(lambda a: _fetch_og_image(a["url"]), missing)
        ):
            if image_url:
                article["thread"]["main_image"] = image_url


def fetch_live_articles(feeds=FEEDS) -> list[dict]:
    """Fetch every feed, merge, dedupe by URL, newest first."""
    merged: dict[str, dict] = {}
    for source, url in feeds:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
                records = parse_feed(response.read(), source)
        except Exception:
            # One bad feed must not sink the others.
            continue
        for record in records:
            merged.setdefault(record["url"], record)
    articles = sorted(
        merged.values(),
        key=lambda record: record["published"],
        reverse=True,
    )
    articles = articles[:MAX_ARTICLES]
    _backfill_images(articles)
    return articles


def refresh_news(redis_client) -> int:
    """Replace the stored feed with live articles.

    Returns how many articles are live now. When the fetch produces
    nothing, the stored entries are left untouched and 0 is returned.
    """
    articles = fetch_live_articles()
    if not articles:
        return 0
    redis_client.save_entry("all_articles", articles)
    return len(articles)


_thread_started = False
_thread_lock = threading.Lock()


def start_refresher(redis_client) -> None:
    """Start the background refresh thread (at most once per process)."""
    global _thread_started
    with _thread_lock:
        if _thread_started:
            return
        _thread_started = True

    def _run() -> None:
        time.sleep(2)
        while True:
            try:
                refresh_news(redis_client)
            except Exception:
                # Never let a refresh error kill the thread or the app.
                pass
            time.sleep(REFRESH_MINUTES * 60)

    threading.Thread(target=_run, name="live-news-refresher", daemon=True).start()
