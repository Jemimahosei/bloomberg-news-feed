# Bloomberg News Feed — Deploy Notes

For the parent agent (jem's main agent). Do NOT push from here without
jem's approval; this file is the handoff for the repo + deploy steps.

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
- **React frontend** (`frontend/`, React 18 + Vite + TypeScript): dark
  terminal-inspired reader — category tabs, ticker chips, search,
  source filter, two-pane headline/detail, honest empty/sample states,
  Tech Lab attribution footer. No market numbers are shown anywhere
  (no fake index values); all content is live RSS or labeled sample data.
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
   Include: `cmd/server/dist/index.html` (placeholder), all Go sources,
   `frontend/src/*`, `frontend/package.json`, `frontend/package-lock.json`,
   `frontend/vite.config.ts`, `frontend/tsconfig.json`,
   `frontend/index.html`, `Dockerfile`, `docker-compose.yml`,
   `render.yaml`, `README.md`, `DEPLOY_NOTES.md`, `.gitignore`,
   `.dockerignore`, `.github/workflows/ci.yml`.
   (Snapshot pushes have a 2,000-file / 16 MiB text-only cap; this repo
   is far under it once node_modules/dist are excluded.)
3. **Render**: create a Blueprint from the repo (render.yaml). It
   creates the `bloomberg-news-feed` Docker web service (free). First
   deploy takes a few minutes (node + Go builds).
4. **Redis (optional)**: for caching, create a free Render Key Value
   instance and paste its internal Redis URL into the service's
   `REDIS_URL` Environment row (the row exists because render.yaml sets
   `sync: false`). Leave it unset and the app still works fully.
5. **Verify live**: `GET /healthz` (articles > 0), open the site URL,
   check headlines load, try a ticker chip and search. First load after
   idle can take ~50s (free tier sleeps).

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
