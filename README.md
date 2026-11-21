# The Tech Lab Times

A full-stack news feed built from the [Bloomberg Tech Lab on Campus](https://bloombergtechlab.github.io/bbit-learning-labs/) project.

**Live site:** https://bloomberg-news-feed.onrender.com

## What it does

- News feed of 25 US financial articles with a featured story on top
- Search articles by keyword, and open any story to read it in full on the site
- Stocks page with live prices, a ticker tape, price charts, and day high/low — quotes refresh every minute

## Stack

Next.js + React frontend, Flask backend, Redis, Docker — the stack the lab specifies. One Render Docker container runs all three.

## Run it locally

```bash
docker compose up --build
```

Then open http://localhost:3000.

Without Docker (needs Python 3.12, Node 20, Redis): `make install`, then `make run-backend` and `make run-frontend` in separate terminals.

## Notes

- The live site is on Render's free tier, so the first load can take about a minute while it wakes up.
- Articles are the lab's own 2018 dataset ([Kaggle](https://www.kaggle.com/datasets/jeet2016/us-financial-news-articles/data)). Not affiliated with Bloomberg L.P.
