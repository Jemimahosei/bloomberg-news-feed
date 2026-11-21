# The Tech Lab Times

## 🔗 Live site: https://bloomberg-news-feed.onrender.com

A full-stack news feed built from the [Bloomberg Tech Lab on Campus](https://bloombergtechlab.github.io/bbit-learning-labs/) project. News feed of 25 US financial articles with a featured story, keyword search, and full article pages — plus a Stocks page with live prices, a ticker tape, price charts, and day high/low, refreshing every minute.

## Architecture

```
Browser ──▶ Next.js (React + TypeScript + Tailwind)
              │  /api/news/* proxy
              ▼
           Flask API (Python, gunicorn)
              │  reads / writes
              ▼
           Redis ◀── lab dataset (25 articles, loaded at startup)
              │
           Live quotes: Yahoo Finance → Nasdaq fallback
```

- **Frontend** (Next.js 15, pages router): renders the feed, search, article pages, and stocks UI. Calls the backend only through its `/api/news/*` proxy routes.
- **Backend** (Flask): serves news from Redis (`/get-newsfeed`, `/get-featured-article`), fetches live quotes and price history with a Yahoo → Nasdaq fallback (`/get-stocks`, `/get-history`), caches quotes in Redis for 120s.
- **Deploy**: one Docker container on Render runs Redis + Flask + Next.js together (`Dockerfile`, `render.yaml`).

## Stack

Next.js 15 · React 19 · TypeScript · Tailwind CSS · Flask · Redis · Docker · Render

## Run it locally

```bash
docker compose up --build
```

Then open http://localhost:3000. Without Docker (needs Python 3.12, Node 20, Redis): `make install`, then `make run-backend` and `make run-frontend` in separate terminals.

## Tests

63 backend tests (`backend/tests/test_stocks.py`, `python -m unittest discover backend/tests`). Frontend builds clean (`npm run build`).

## Notes

- The live site is on Render's free tier, so the first load can take about a minute while it wakes up.
- Articles are the lab's own 2018 dataset ([Kaggle](https://www.kaggle.com/datasets/jeet2016/us-financial-news-articles/data)). Not affiliated with Bloomberg L.P.
