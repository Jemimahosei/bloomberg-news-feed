# Bloomberg News Feed — Deploy Notes

For the parent agent (jem's main agent). Do NOT push from here without
jem's approval; this file is the handoff for the repo + deploy steps.

## VERBATIM RESTRUCTURE (Nov 6, 2026 — jem: "follow the workshop instructions verbatim")

The first build's dark-terminal two-pane reader did NOT match the
organizers' layout, so the frontend was rebuilt to follow the
workshop's Frontend Tasks page
(https://bloombergtechlab.github.io/bbit-learning-labs/frontend/)
part by part:

- **Part 1 — FeaturedNews** (`frontend/src/components/FeaturedNews.tsx`):
  ONE featured article at the TOP of the page — title, image, and a
  truncated portion of the body. The featured article is the newest
  article in the store.
- **Part 2 — NewsCard** (`frontend/src/components/NewsCard.tsx`):
  reusable card for general stories — title, image, truncated body.
  Used for every story in the feed.
- **Part 3 — NewsFeed** (`frontend/src/components/NewsFeed.tsx`):
  a GRID of NewsCards at the BOTTOM of the page, under Featured News.
- **Part 4 — API integration**: the frontend fetches the featured
  article from `GET /api/news/get-featured-article` and the feed from
  `GET /api/news/get-newsfeed` (new Go endpoints below).
- **Page structure is now**: header → Featured News → News Feed grid →
  footer. DROPPED (not in the workshop spec): category tabs, ticker
  chips, source filter dropdown, search box, and the two-pane
  list/detail view. The old `/api/headlines`, `/api/search`,
  `/api/articles/{id}`, `/api/categories`, `/api/sources`, `/healthz`
  endpoints still exist and work unchanged — the frontend just no
  longer calls them.
- **Styling**: the organizers call the starter "a pretty plain website"
  and say to look at Bloomberg News for inspiration. The existing dark
  terminal styling is kept as that Bloomberg-inspired look
  (near-black bg #0b0d10, amber accent #f5a623, monospace chrome,
  header with NEWSFEED / Market News Terminal + clock + headline count
  + updated time, footer with the Tech Lab attribution).

### Images — feed-provided only, with a designed fallback

- The RSS parser (`internal/feed/rss.go`, `pickImage`) now captures an
  image URL per article from `media:content` (image medium/type first),
  then any `media:content`, then `media:thumbnail`, then an image
  `enclosure`. Audio enclosures are never used as images. URLs are
  normalized (protocol-relative `//…` gets `https:`); anything that is
  not an http(s) URL is dropped. **No article pages are fetched and no
  images are scraped.**
- Exposed as `image_url` in the article JSON (`omitempty` — absent
  when the feed provides none). Live coverage on Nov 6, 2026: **65 of
  100 sampled articles carry a feed image** (MarketWatch, Guardian,
  Investing.com, Ars Technica, BBC all provide them); CNBC, NPR, and
  Hacker News provide none.
- Where a feed provides no image (or its image fails to load), the UI
  renders a **designed fallback tile** (`ArticleImage` component):
  dark tile with the source's initial in amber monospace + the
  category + a small "No image from feed" caption. NEVER fake photos,
  stock photos, scraped images, or invented image URLs.
- The featured story is excluded from the grid below it so the same
  article is not shown twice on one page.

### Go backend kept — deviation from the workshop's Flask (deliberate)

The workshop's backend is Flask; this build keeps the **Go backend**
per jem's own earlier instruction (Go + Redis) and because the Go
service is already live and working. No Bloomberg code is copied
either way. The only backend change is additive: the two workshop
endpoints above plus image extraction. `render.yaml` and the
`Dockerfile` are unchanged (same single Docker service).

### Verification (this restructure, Nov 6 2026 ~17:45 UTC, all in VM)

- `go vet ./...` clean; `go test -count=1 ./...` — all packages pass,
  including new tests: `TestParseRSSImages` (media:content >
  media:thumbnail > image enclosure; audio enclosure ignored;
  protocol-relative URL normalized) and `TestNewsEndpoints` (featured
  = newest article; newsfeed list + limit; empty store → featured 404,
  newsfeed empty) plus `TestFeatured` in the store tests.
- `npm run build` (tsc + vite) clean — 148.53 kB JS, 47.87 kB gzip.
- **Live server run** (PORT 18080): ingested **279 real articles**;
  `/api/news/get-featured-article` returns the newest article;
  `/api/news/get-newsfeed` returns the list (65/100 with `image_url`);
  `/api/headlines`, `/api/search`, `/api/categories`, `/api/sources`,
  `/api/articles/{id}`, `/healthz` all still 200; `/` serves the new
  build (200) and the JS asset serves 200; the built bundle contains
  "Featured News", "News Feed", and "image-fallback" markers and zero
  occurrences of "Tickers".
- **NOT verified here**: the UI in a real browser (no browser tool in
  this session) — the parent should visually confirm the featured
  section + card grid after deploy; the Docker build and Render
  redeploy (same as before — the CI `docker` job builds on push).

## Origin (verified)

- jem was accepted to the **Bloomberg Tech Lab on Campus at Cornell**
  (acceptance email `1955ccf40a97aaf0`, Mar 3 2025, from Brittany Koempel /
  `blprecruiting@recruiting.bloomberg.com`; event Mar 6 2025, Statler
  Hotel Taylor Room).
- The lab's guide is http://bloombergtechlab.github.io/bbit-learning-labs/
  (React + Flask + Redis + Docker; repo
  https://github.com/bloomberg/bbit-learning-labs, NewsFeed under
  `Tech-Lab-On-Campus/NewsFeed`). This build follows the lab's *product
  shape* (a news feed) but is an **original Go implementation** — no
  Bloomberg code is copied. jem's instruction for this build was Go +
  Redis, so the Go backend from the existing partial was kept and
  completed.

## What was built in this session (starting from the Go partial)

The partial already had a working Go API (RSS ingest, in-memory store,
RESP Redis client, handlers, tests, Dockerfile, compose). Added:

- **Market feeds** (`internal/feed/rss.go`): MarketWatch, CNBC Markets,
  Investing.com, CNBC, The Guardian Business — all verified HTTP 200 +
  valid RSS from this VM in Nov 2026. Yahoo Finance RSS (404) and
  Reuters business RSS (401) were checked and deliberately excluded.
  New `markets` category; 11 sources, 5 categories total.
- **Ticker filter**: `GET /api/headlines?ticker=AAPL` (token-based match,
  so `AAPL` never matches `AAPLX`); `GET /api/sources` endpoint;
  `updated_at` in `/healthz` (last ingest time).
- **Redis URL support** (`internal/cache/cache.go`, `cmd/server/main.go`):
  `REDIS_URL` (e.g. `redis://:password@host:6379/0`, as Render Key Value
  provides) takes precedence over `REDIS_ADDR`; the RESP client now
  sends AUTH and SELECT. `rediss://` (TLS) is rejected with a clear
  error. No Redis → in-memory serving, unchanged.
- **React frontend** (`frontend/`, React 18 + Vite + TypeScript):
  originally a dark terminal-inspired two-pane reader (category tabs,
  ticker chips, search, source filter, headline list + detail pane).
  **REBUILT Nov 6, 2026 to follow the workshop instructions verbatim**
  — see the "VERBATIM RESTRUCTURE" section above (FeaturedNews on top,
  NewsCard grid below, workshop API endpoints, feed images + fallback
  tiles; tabs/tickers/search/detail pane removed). No market numbers
  are shown anywhere (no fake index values); all content is live RSS
  or labeled sample data.
- **Single-service serving**: the Go binary embeds `frontend/dist` and
  serves the UI + API from one port (no CORS, no API-URL guessing).
  `cmd/server/dist/index.html` is a placeholder page when the frontend
  hasn't been built; the Dockerfile overwrites it with the real build.
- **Deploy files**: `render.yaml` (one free Docker web service
  `bloomberg-news-feed`, `REDIS_URL` as `sync: false` so the dashboard
  shows the row), multi-stage `Dockerfile` (node → Go → alpine),
  `.dockerignore`, CI gained frontend + docker-build jobs.
- **Date fix**: Investing.com emits bare `YYYY-MM-DD HH:MM:SS` pubDates
  (and no descriptions); the parser now handles that layout.
- **Tests added**: ticker matching, sources/last-updated, `redis://`
  URL parsing, AUTH/SELECT round trip against the fake RESP server,
  ticker + sources handler tests.

## Verification (all done in this VM, Nov 6 2026 ~03:20–03:30 UTC)

- Go 1.23.4 installed from the official tarball to `~/go` (go.dev
  reachable; `go` was not previously installed). Not committed; the
  Dockerfile uses `golang:1.23-alpine`.
- `go vet ./...` clean; `go test ./...` — all packages pass (api, cache,
  feed, store).
- `npm --prefix frontend run build` — clean (tsc + vite; 149.54 kB JS,
  48.36 kB gzip).
- **Live server run** (`/tmp/newsfeed`, PORT 18080): ingested **286 real
  articles from 11 sources** on first boot; `/healthz` returns
  `{"articles":286,"status":"ok","updated_at":...}`; `/api/categories`
  returns all 5 categories; `/api/sources` returns all 11 sources;
  ticker `LBRT` matched the live "LBRT stock" headline; `/api/search?q=`
  works; article detail returns `X-Cache: MISS`; `/` serves the React
  app (200, correct HTML); SPA fallback (`/some-route`) returns 200.
- **Redis verified end to end** against a Python fake RESP server on
  127.0.0.1:16399 (no real Redis exists in this VM): `REDIS_ADDR` →
  connected, repeat request `X-Cache: MISS` then `HIT`; `REDIS_URL`
  with password + db index → connected, AUTH/SELECT accepted, MISS→HIT.
- **Vite dev proxy verified**: `npm run dev` serves the page (200) and
  proxies `/api/*` + `/healthz` to the Go server (with
  `VITE_API_PROXY=http://localhost:18080`).
- **NOT verified here**: the Docker image build (no Docker in this VM —
  the CI `docker` job builds it on push), and the Render deploy itself.

## Deploy steps for the parent

1. **Create a new GitHub repo** `Jemimahosei/bloomberg-news-feed`
   (public; the Muse GitHub App cannot create repos — create it via the
   browser while signed in as jem, then add it to the app installation
   like Gradebook-Ghana).
2. **Snapshot-push** the project (source dir
   `~/workspace/projects/bloomberg-news-feed/`). Push everything EXCEPT:
   `frontend/node_modules/`, `frontend/dist/`, `cmd/server/dist/assets/`
   (build outputs — the Dockerfile regenerates them), `/tmp` files.
   Include: `cmd/server/dist/index.html` (placeholder — the Dockerfile
   regenerates it; the local copy currently holds the latest built
   index.html from verification, which is fine to push), all Go
   sources, `frontend/src/*` (including the new
   `frontend/src/components/FeaturedNews.tsx`, `NewsCard.tsx`,
   `NewsFeed.tsx`, `ArticleImage.tsx`), `frontend/package.json`,
   `frontend/package-lock.json`, `frontend/vite.config.ts`,
   `frontend/tsconfig.json`, `frontend/index.html`, `Dockerfile`,
   `docker-compose.yml`, `render.yaml`, `README.md`, `DEPLOY_NOTES.md`,
   `.gitignore`, `.dockerignore`.
   **NEVER include `.github/workflows/ci.yml`** (or anything under
   `.github/workflows/`): GitHub refuses to let a GitHub App create
   workflow files via the git-trees API, so the WHOLE tree creation
   fails with 403 "Resource not accessible by integration" — this was
   the cause of the first push's 4 consecutive failures (the App
   installation was already "All repositories"). Add CI files via the
   web UI if wanted; they are never needed for a Render deploy.
   (Snapshot pushes have a 2,000-file / 16 MiB text-only cap; this repo
   is far under it once node_modules/dist are excluded.)
3. **Render**: create a Blueprint from the repo (render.yaml). It
   creates the `bloomberg-news-feed` Docker web service (free). First
   deploy takes a few minutes (node + Go builds).
4. **Redis (optional)**: for caching, create a free Render Key Value
   instance and paste its internal Redis URL into the service's
   `REDIS_URL` Environment row (the row exists because render.yaml sets
   `sync: false`). Leave it unset and the app still works fully.
5. **Verify live**: `GET /healthz` (articles > 0),
   `GET /api/news/get-featured-article` (returns one article),
   `GET /api/news/get-newsfeed` (returns the list), open the site URL
   and confirm the Featured News section renders at the top and the
   News Feed grid renders below it (with feed images where provided
   and fallback tiles where not). First load after idle can take ~50s
   (free tier sleeps).

## Known limitations / notes

- Port 8080 in this VM is occupied by an unrelated Java process, so all
  local runs used PORT 18080 (and `VITE_API_PROXY` for the dev server).
  On jem's Mac / Render, the default 8080 is fine.
- Investing.com items have no description text — those cards render
  title-only, which is honest (the description genuinely doesn't exist
  in that feed).
- The `X-Cache` header reads `MISS` on every request when no Redis is
  configured (NoopCache) — expected, not a bug.
- No secrets anywhere in the repo. No API keys are needed (RSS only).
