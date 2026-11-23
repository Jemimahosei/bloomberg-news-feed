"""Flask app instance creation for Tech Lab 2025."""

import os
from dataclasses import asdict

from flask import Flask, Response, jsonify, request

from app import live_news, newsfeed, stocks
from app.utils.file_loader import load_json_files
from app.utils.redis import REDIS_CLIENT


def _to_json(article: newsfeed.Article) -> dict:
    """Convert an article to a JSON friendly dict."""
    data = asdict(article)
    data["publish_date"] = article.publish_date.isoformat()
    return data


def create_app():
    """Create a Flask app instance."""
    app = Flask("app")

    # Load JSON files into Redis. The bundled dataset is only the
    # seed/fallback — it is a fixed set of 2018 articles, so on its
    # own the feed would show the same stories forever.
    dataset_directory = os.path.join(os.path.dirname(__file__), "../resources/dataset/news")
    REDIS_CLIENT.save_entry("all_articles", load_json_files(dataset_directory))

    # Live headlines: a background thread replaces the seed with
    # current RSS articles shortly after startup and refreshes them
    # every 30 minutes. Set NEWS_LIVE_REFRESH=off to keep the seed.
    if os.environ.get("NEWS_LIVE_REFRESH", "on").lower() != "off":
        live_news.start_refresher(REDIS_CLIENT)

    @app.route("/ping", methods=["GET"])
    def ping() -> Response:
        """Flask route to check if the server is up and running."""
        return jsonify("Pong!", 200)

    @app.route("/get-newsfeed", methods=["GET"])
    def get_newsfeed() -> Response:
        """Flask route to get the latest newsfeed from datastore."""
        return jsonify([_to_json(article) for article in newsfeed.get_all_news()])

    @app.route("/get-featured-article", methods=["GET"])
    def get_featured_article() -> Response:
        """Flask route to get the featured article from datastore."""
        article = newsfeed.get_featured_news()
        return jsonify(_to_json(article) if article else None)

    @app.route("/get-stocks", methods=["GET"])
    def get_stocks_route() -> Response:
        """Flask route to get stock quotes.

        No query param serves the default watchlist; ?symbols=AAPL,MSFT
        looks up the given tickers.
        """
        raw = request.args.get("symbols")
        symbols = stocks.clean_symbols(raw) if raw is not None else None
        quotes = stocks.get_stocks(symbols)
        return jsonify([stocks.quote_to_dict(quote) for quote in quotes])

    @app.route("/get-history", methods=["GET"])
    def get_history_route() -> Response:
        """Flask route to get a price history for one ticker.

        ?symbol=AAPL serves the past month of daily closes (Yahoo),
        falling back to the current session (Nasdaq) when Yahoo fails.
        """
        raw = request.args.get("symbol", "")
        symbols = stocks.clean_symbols(raw)
        if not symbols:
            return (
                jsonify(
                    {"symbol": raw, "source": None, "label": "", "points": [], "error": "not_found"}
                ),
                400,
            )
        history = stocks.get_history(symbols[0])
        return jsonify(stocks.history_to_dict(history))

    return app
