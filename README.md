# Bloomberg-Style News Feed

A full-stack market news aggregator: a Go REST API that ingests free
public RSS feeds on a schedule, caches responses in Redis, and serves a
React news feed — a Featured News story on top and a grid of news cards
below — from a single service. No API keys, no accounts,
no third-party Go dependencies (the standard library only; the Redis
client speaks RESP directly over TCP).

Built by Jemimah Osei as a portfolio project, following the **Bloomberg
Tech Lab on Campus at Cornell** (March 6, 2025, Statler Hotel), where she
was accepted to build a full-stack News Feed with Bloomberg engineers.
The lab's own guide is
[bloombergtechlab.github.io/bbit-learning-labs](http://bloombergtechlab.github.io/bbit-learning-labs/).
This is an original implementation in Go (the lab used Flask) — no
Bloomberg code is copied. Not affiliated with Bloomberg L.P.

## What it does

- Ingests 11 free public RSS feeds (MarketWatch, CNBC, Investing.com,
  BBC News/Business, The Guardian, NPR, Hacker News, Ars Technica),
  normalized into one feed across five categories: `markets`,
  `business`, `general`, `world`, `technology`.
- Caches API responses in Redis when `REDIS_URL`/`REDIS_ADDR` is set and
  falls back to the in-memory store when it is not — the app always
  works, with or without Redis.
- The React frontend follows the Tech Lab workshop layout verbatim: a
  Featured News section on top (one featured article — title, image,
  truncated body) and a News Feed grid below it (reusable news cards
  with title, image, truncated body). Images come only from the feeds
  themselves; stories without one get a designed fallback tile. The
  page keeps the dark terminal styling (near-black background, amber
  accent, monospace header). The API also still supports headline
  search and category/source/ticker filters for API clients.

## Quick start (Docker)

```bash
docker compose up --build
```

Open http://localhost:8080 — the API and the UI share that port.

## Quick start (local)

```bash
# Backend (Go 1.23+). Runs without Redis; set REDIS_ADDR for caching.
go run ./cmd/server

# Frontend dev server (proxies /api to the Go server on :8080).
npm --prefix frontend install
npm --prefix frontend run dev   # http://localhost:5173

# Production frontend build, embedded into the Go binary:
npm --prefix frontend install && npm --prefix frontend run build
cp -r frontend/dist/. cmd/server/dist/
go build -o newsfeed ./cmd/server && ./newsfeed
```

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8080` | HTTP port |
| `REDIS_URL` | _(unset)_ | Redis URL, e.g. `redis://:password@host:6379/0`. Takes precedence over `REDIS_ADDR`. Unset = no caching |
| `REDIS_ADDR` | _(unset)_ | Redis address, e.g. `localhost:6379`. Only used when `REDIS_URL` is unset |
| `CACHE_TTL_SECONDS` | `60` | TTL for cached API responses |
| `INGEST_INTERVAL_MINUTES` | `15` | RSS refresh interval |

## Endpoints

### Health

```bash
curl localhost:8080/healthz
# {"articles":286,"status":"ok","updated_at":"2026-11-06T03:21:09Z"}
```

### Workshop endpoints (what the frontend uses)

```bash
curl "localhost:8080/api/news/get-featured-article"
curl "localhost:8080/api/news/get-newsfeed?limit=50"
```

`get-featured-article` returns the single newest article as
`{"data": {...}}`; `get-newsfeed` returns the newest-first list as
`{"data": [...], "count": N}`. Articles carry an `image_url` when the
RSS feed supplied one (omitted otherwise).

### Latest headlines

```bash
curl "localhost:8080/api/headlines?limit=5"
```

```json
{
  "data": [
    {
      "id": "59cb210a04df48c4",
      "title": "Chinese firms’ profit margins trail global peers",
      "description": "",
      "url": "https://www.investing.com/news/...",
      "source": "Investing.com",
      "category": "markets",
      "published_at": "2026-11-06T03:12:50Z"
    }
  ],
  "count": 5
}
```

### Filter by category, source and/or ticker

```bash
curl "localhost:8080/api/headlines?category=markets"
curl "localhost:8080/api/headlines?source=CNBC"
curl "localhost:8080/api/headlines?ticker=AAPL"
curl "localhost:8080/api/headlines?category=markets&ticker=NVDA&limit=10"
```

The ticker filter matches the symbol as a standalone token in the title
or description (`AAPL`, `$AAPL`, `(AAPL)`), so `AAPL` never matches
`AAPLX`.

### Search by keyword

Searches titles and descriptions (case-insensitive):

```bash
curl "localhost:8080/api/search?q=inflation"
curl "localhost:8080/api/search?q=battery&limit=5"
```

### Single-article detail

```bash
curl localhost:8080/api/articles/59cb210a04df48c4
# {"data": { …article… }}

curl localhost:8080/api/articles/does-not-exist
# {"error":"article not found"}  (404)
```

### Categories and sources

```bash
curl localhost:8080/api/categories   # {"data":["business","general","markets","technology","world"],"count":5}
curl localhost:8080/api/sources      # distinct sources currently present
```

### Caching

List/detail responses are cached in Redis with the configured TTL. The
`X-Cache` response header shows `HIT` or `MISS`, so the cache layer is
visible when demoing. If Redis is down, the API keeps serving from memory
— caching is best-effort and never breaks a request.

## Ingestion & demo notes

- **Sources** (all free, public RSS, no keys): MarketWatch, CNBC Markets,
  Investing.com, CNBC, BBC Business, The Guardian Business, BBC News,
  NPR, The Guardian (World), Hacker News, Ars Technica. See
  `internal/feed/rss.go` for the feed list. Yahoo Finance RSS and Reuters
  business RSS were checked in Nov 2026 and are not usable (404 / 401),
  so they are intentionally not listed.
- **Schedule:** ingestion runs once at startup, then every
  `INGEST_INTERVAL_MINUTES` minutes. A failed tick is logged and the
  previous articles keep serving; it never empties the store.
- **Seed/demo behavior:** on first run, if live RSS yields nothing (no
  network, feeds down), the API seeds itself from the bundled sample
  dataset in `internal/feed/sample.json` (10 demo articles across all
  five categories), so the API always demonstrates end-to-end. Sample
  articles are marked with source `Sample Wire`, and the frontend shows
  a banner when everything on screen is sample data. All other content
  is live from the feeds — nothing is fabricated.
- **Deduplication:** articles are keyed by a hash of their URL, so
  re-ingesting the same feed never duplicates stories.
- **Feed quirks:** Investing.com items carry no description and a bare
  `YYYY-MM-DD HH:MM:SS` date; the parser handles both (see
  `parsePubDate`).

## Project layout

```
cmd/server/            entrypoint: env config, Redis probe, scheduler,
                       HTTP server + embedded React frontend (dist/)
frontend/              React 18 + Vite + TypeScript news terminal
internal/model/        Article type
internal/feed/         RSS parsing, feed list, ingestion scheduler, sample data
internal/store/        thread-safe in-memory article store (list/search/ticker/get)
internal/cache/        Cache interface, NoopCache, minimal RESP Redis client
                       (AUTH/SELECT, redis:// URL parsing)
internal/api/          HTTP handlers + routes, X-Cache headers
Dockerfile             node build -> Go build -> slim runtime image
docker-compose.yml     api + redis services
render.yaml            Render Blueprint: one free Docker web service
.github/workflows/ci.yml  Go build/vet/test + frontend build + docker build
```

## Tests

```bash
go test ./...
```

Tests cover RSS parsing (multi-format dates, HTML stripping, ID
stability), store filtering/search/ticker/ordering, the Redis client
against an in-process fake RESP server (including AUTH, dead-Redis
degradation and `redis://` URL parsing), and the HTTP handlers including
`X-Cache` HIT/MISS behavior.

## Deploy (Render)

`render.yaml` defines one free Docker web service (`bloomberg-news-feed`)
that serves the API and the UI. Create a Blueprint from this repo in the
Render dashboard and it builds from the Dockerfile. `REDIS_URL` is
optional — to enable Redis caching, create a free Render Key Value
instance and paste its internal Redis URL into the `REDIS_URL` row in
the service's Environment settings. Render free web services sleep after
inactivity, so the first load after idle can take ~50s.
