"""Module for retrieving newsfeed information."""

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from app.utils.redis import REDIS_CLIENT


@dataclass
class Article:
    """Dataclass for an article."""

    author: str
    title: str
    body: str
    publish_date: datetime
    image_url: str
    url: str


def get_all_news() -> list[Article]:
    """Get all news articles from the datastore."""
    all_articles: list[dict] = REDIS_CLIENT.get_entry("all_articles")

    if all_articles is None:
        return []

    articles = [_format_as_article(article) for article in all_articles]
    # Most recent first, the order a newsfeed is read in.
    return sorted(articles, key=lambda article: article.publish_date, reverse=True)


def get_featured_news() -> Article | None:
    """Get the featured news article from the datastore."""
    # can be this or some criteria to decide which is featured.
    all_news = get_all_news()

    if not all_news:
        return None
    return max(all_news, key=lambda article: article.publish_date)


def _rewrite_image_url(url: str) -> str:
    """Rewrite an fm.cnbc.com image URL to its image.cnbcfm.com form.

    Plain requests to fm.cnbc.com images return 403; the same image is
    served from image.cnbcfm.com/api/v1/image/<basename> (the target of
    the 301 a browser User-Agent receives). Any other URL is returned
    unchanged.
    """
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.netloc.lower() != "fm.cnbc.com":
        return url
    basename = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    if not basename:
        return url
    return f"https://image.cnbcfm.com/api/v1/image/{basename}"


def _format_as_article(data: dict) -> Article:
    return Article(
        author=data["author"],
        title=data["title"],
        body=data["text"],
        publish_date=datetime.fromisoformat(data["published"]),
        image_url=_rewrite_image_url(data["thread"]["main_image"]),
        url=data["url"],
    )
