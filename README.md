# The Tech Lab Times: Bloomberg Tech Lab News Feed

A full stack news feed built from the Bloomberg Tech Lab on Campus project
([lab guide](https://bloombergtechlab.github.io/bbit-learning-labs/),
[original lab repo](https://github.com/bloomberg/bbit-learning-labs), which I
worked on through my fork,
[bbit-learning-labs](https://github.com/Jemimahosei/bbit-learning-labs)).

**Live site:** https://bloomberg-news-feed.onrender.com
(Render's free tier sleeps when idle, so the first load can take about a minute.)

## Stack

The same stack the lab specifies:

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 15 (pages router), React 19, TypeScript, Tailwind CSS |
| Backend | Flask (Python 3.12), served with gunicorn |
| Cache and data store | Redis |
| Packaging | Docker and Docker Compose |

## How it works

1. On startup the Flask app loads the lab's dataset of US financial news
   articles (`backend/resources/dataset/news`) into Redis.
2. `GET /get-newsfeed` reads the articles back from Redis, formats them as
   `Article` objects and returns them newest first.
3. `GET /get-featured-article` returns the most recent article.
4. The Next.js frontend calls them through its own proxy route,
   `/api/news/get-newsfeed` and `/api/news/get-featured-article`, and renders
   a **Featured News** story, a grid of reusable **News Cards**, and a
   sidebar of more stories.

## Run it locally

With Docker:

```bash
docker compose up --build
```

Then open http://localhost:3000.

Without Docker (needs Python 3.12, Node 20 and Redis):

```bash
make install
redis-server &
make run-backend      # http://localhost:8000
make run-frontend     # http://localhost:3000, in another terminal
```

## Deploying

`render.yaml` is a Render Blueprint for one free Docker web service. The root
`Dockerfile` runs Redis, the Flask API and the Next.js server together in a
single container and `start.sh` wires them up.

## Where this differs from the lab starter

The lab hands students a skeleton with blanks. This repo is the finished
version, with three small changes from the lab's own solution:

- The solution sorted articles with a call that raises an error. It now sorts
  by publish date correctly.
- The lab stylesheet let long titles overlap and broke on phones. The look is
  unchanged (orange masthead, dark nav bar, featured story, three column grid,
  sidebar) but titles wrap and the grid is responsive.
- The front page, `/`, goes straight to the news feed.

Dataset: [US Financial News Articles](https://www.kaggle.com/datasets/jeet2016/us-financial-news-articles/data)
on Kaggle. Not affiliated with Bloomberg L.P.
