"""Tests for app.newsfeed."""

import unittest

from app.newsfeed import _format_as_article, _rewrite_image_url


def _article_data(image_url: str) -> dict:
    """Build a minimal dataset record with the given image URL."""
    return {
        "author": "Test Author",
        "title": "Test Title",
        "text": "Test body.",
        "published": "2018-01-02T00:00:00",
        "thread": {"main_image": image_url},
        "url": "https://example.com/test",
    }


class TestRewriteImageUrl(unittest.TestCase):
    """Tests for _rewrite_image_url."""

    def test_fm_cnbc_url_rewritten_to_image_cnbcfm(self):
        """An fm.cnbc.com URL is rewritten to image.cnbcfm.com."""
        url = (
            "https://fm.cnbc.com/applications/cnbc.com/resources/img/editorial/"
            "2018/05/15/105209479-GettyImages-957425524.1910x1000.jpg"
        )
        self.assertEqual(
            _rewrite_image_url(url),
            "https://image.cnbcfm.com/api/v1/image/105209479-GettyImages-957425524.1910x1000.jpg",
        )

    def test_non_fm_cnbc_url_unchanged(self):
        """A URL on any other host passes through unchanged."""
        url = "https://example.com/images/photo.jpg"
        self.assertEqual(_rewrite_image_url(url), url)

    def test_empty_url_unchanged(self):
        """An empty URL passes through unchanged."""
        self.assertEqual(_rewrite_image_url(""), "")

    def test_fm_cnbc_url_without_basename_unchanged(self):
        """An fm.cnbc.com URL with no image file passes through unchanged."""
        self.assertEqual(_rewrite_image_url("https://fm.cnbc.com/"), "https://fm.cnbc.com/")

    def test_format_as_article_rewrites_image_url(self):
        """_format_as_article serves the rewritten image URL."""
        article = _format_as_article(
            _article_data(
                "https://fm.cnbc.com/applications/cnbc.com/resources/img/editorial/"
                "2018/01/02/104924752-GettyImages-895470622.1910x1000.jpg"
            )
        )
        self.assertEqual(
            article.image_url,
            "https://image.cnbcfm.com/api/v1/image/104924752-GettyImages-895470622.1910x1000.jpg",
        )

    def test_format_as_article_keeps_other_image_url(self):
        """_format_as_article keeps a non-fm.cnbc.com image URL as-is."""
        article = _format_as_article(_article_data("https://example.com/images/photo.jpg"))
        self.assertEqual(article.image_url, "https://example.com/images/photo.jpg")


if __name__ == "__main__":
    unittest.main()
