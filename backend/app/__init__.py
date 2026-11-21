"""Flask app instance creation for Tech Lab 2025."""

import os
from dataclasses import asdict

from flask import Flask, Response, jsonify, request

from app import newsfeed, stocks
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

    # Load JSON files into Redis
    dataset_directory = os.path.join(os.path.dirname(__file__), "../resources/dataset/news")
    REDIS_CLIENT.save_entry("all_articles", load_json_files(dataset_directory))

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

    return app
