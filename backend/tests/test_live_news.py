"""Tests for app.live_news — parsing and merging, no network."""

import io
import unittest
import urllib.request
from unittest import mock

from app import live_news
from app.newsfeed import _format_as_article

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:media="http://search.yahoo.com/mrss/"
     xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Example Business</title>
    <item>
      <title>Markets rally &amp; tech leads</title>
      <link>https://example.com/story-1</link>
      <description>&lt;p&gt;Stocks rose today.&lt;/p&gt;</description>
      <pubDate>Sun, 22 Nov 2026 17:14:03 GMT</pubDate>
      <dc:creator>Jane Reporter</dc:creator>
      <media:thumbnail url="https://img.example.com/one.jpg" />
    </item>
    <item>
      <title>Older story</title>
      <link>https://example.com/story-2</link>
      <description>Plain description, no image.</description>
      <pubDate>Sat, 21 Nov 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class TestParseFeed(unittest.TestCase):
    """parse_feed maps RSS items into the dataset record shape."""

    def test_records_match_dataset_shape(self):
        records = live_news.parse_feed(RSS, "Example")
        self.assertEqual(len(records), 2)
        first = records[0]
        self.assertEqual(first["title"], "Markets rally & tech leads")
        self.assertEqual(first["author"], "Jane Reporter")
        self.assertEqual(first["text"], "Stocks rose today.")
        self.assertEqual(first["url"], "https://example.com/story-1")
        self.assertTrue(first["published"].startswith("2026-11-22T17:14:03"))
        self.assertEqual(first["thread"]["main_image"], "https://img.example.com/one.jpg")

    def test_missing_image_and_creator_fall_back(self):
        records = live_news.parse_feed(RSS, "Example")
        second = records[1]
        self.assertEqual(second["thread"]["main_image"], "")
        self.assertEqual(second["author"], "Example")

    def test_records_feed_the_existing_formatter(self):
        """A parsed record must survive newsfeed._format_as_article."""
        article = _format_as_article(live_news.parse_feed(RSS, "Example")[0])
        self.assertEqual(article.title, "Markets rally & tech leads")
        self.assertEqual(article.image_url, "https://img.example.com/one.jpg")
        self.assertEqual(article.publish_date.year, 2026)


class TestFetchLiveArticles(unittest.TestCase):
    """fetch_live_articles merges feeds, dedupes, sorts newest first."""

    def test_merge_dedupe_sort(self):
        def fake_urlopen(request, timeout=0):
            return io.BytesIO(RSS)

        with mock.patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            articles = live_news.fetch_live_articles(
                feeds=[("Example", "https://a/rss"), ("Example", "https://b/rss")]
            )
        # The same two stories arrive from both feeds — deduped by URL.
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["url"], "https://example.com/story-1")

    def test_one_bad_feed_does_not_sink_the_others(self):
        def flaky_urlopen(request, timeout=0):
            if "bad" in request.full_url:
                raise OSError("feed down")
            return io.BytesIO(RSS)

        with mock.patch.object(urllib.request, "urlopen", side_effect=flaky_urlopen):
            articles = live_news.fetch_live_articles(
                feeds=[("Example", "https://bad/rss"), ("Example", "https://good/rss")]
            )
        self.assertEqual(len(articles), 2)


if __name__ == "__main__":
    unittest.main()
