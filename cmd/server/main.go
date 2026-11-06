// Command newsfeed runs the Bloomberg-style news API: it ingests public
// RSS feeds on a schedule, caches API responses in Redis, and serves
// headlines, search, filters, and article detail over HTTP. It also serves
// the bundled React frontend (frontend/dist, embedded at build time) from
// the same port, so one service is the whole product.
//
// Configuration (environment variables):
//
//	PORT                    HTTP port (default 8080)
//	REDIS_URL               Redis URL, e.g. redis://:password@host:6379/0.
//	                        Takes precedence over REDIS_ADDR. Empty means
//	                        run without caching (responses still served).
//	REDIS_ADDR              Redis address, e.g. localhost:6379. Only used
//	                        when REDIS_URL is unset.
//	CACHE_TTL_SECONDS       Redis TTL for API responses (default 60)
//	INGEST_INTERVAL_MINUTES RSS refresh interval (default 15)
package main

import (
	"context"
	"embed"
	"io/fs"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"newsfeed/internal/api"
	"newsfeed/internal/cache"
	"newsfeed/internal/feed"
	"newsfeed/internal/store"
)

//go:embed dist
var frontendFS embed.FS

// frontendHandler serves the embedded React build with SPA fallback.
// cmd/server/dist/index.html is a placeholder page when the frontend has
// not been built yet; `npm run build` in frontend/ replaces it (see the
// Dockerfile and README). API paths never reach here: more specific
// /api/* and /healthz routes win in the mux.
func frontendHandler() http.Handler {
	sub, err := fs.Sub(frontendFS, "dist")
	if err != nil {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			http.Error(w, "frontend not built", http.StatusNotFound)
		})
	}
	fileServer := http.FileServer(http.FS(sub))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// SPA fallback: unknown extensionless paths render the app shell,
		// which routes client-side.
		if r.URL.Path != "/" && !strings.Contains(r.URL.Path, ".") {
			if _, err := fs.Stat(sub, strings.TrimPrefix(r.URL.Path, "/")); err != nil {
				r.URL.Path = "/"
			}
		}
		if strings.HasPrefix(r.URL.Path, "/assets/") {
			w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
		} else {
			w.Header().Set("Cache-Control", "no-cache")
		}
		fileServer.ServeHTTP(w, r)
	})
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	v, err := strconv.Atoi(os.Getenv(key))
	if err != nil || v <= 0 {
		return def
	}
	return v
}

func main() {
	port := envOr("PORT", "8080")
	ttl := time.Duration(envInt("CACHE_TTL_SECONDS", 60)) * time.Second
	interval := time.Duration(envInt("INGEST_INTERVAL_MINUTES", 15)) * time.Minute

	st := store.New()

	// Redis is best-effort: if it is unreachable we keep serving from the
	// in-memory store and log the fact instead of crashing. REDIS_URL
	// (redis://[:password@]host:port[/db], as provided by hosted Redis
	// services such as Render Key Value) takes precedence over REDIS_ADDR.
	var c cache.Cache = cache.NoopCache{}
	redisAddr := os.Getenv("REDIS_ADDR")
	redisPassword := ""
	redisDB := 0
	if u := os.Getenv("REDIS_URL"); u != "" {
		addr, pw, db, err := cache.ParseRedisURL(u)
		if err != nil {
			log.Printf("redis: REDIS_URL invalid (%v); continuing without cache", err)
		} else {
			redisAddr, redisPassword, redisDB = addr, pw, db
		}
	}
	if redisAddr != "" {
		rc := &cache.RedisCache{Addr: redisAddr, Password: redisPassword, DB: redisDB}
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		err := rc.Ping(ctx)
		cancel()
		if err != nil {
			log.Printf("redis: %s unreachable (%v); continuing without cache", redisAddr, err)
		} else {
			log.Printf("redis: connected to %s (TTL %s)", redisAddr, ttl)
			c = rc
		}
	} else {
		log.Printf("redis: REDIS_URL/REDIS_ADDR unset; running without cache")
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// First run: live RSS, or the bundled sample dataset when the network
	// is unavailable, so the API always demonstrates end-to-end.
	feed.EnsureSeeded(ctx, st)
	go feed.StartScheduler(ctx, st, interval)

	srv := &api.Server{Store: st, Cache: c, TTL: ttl}
	mux := srv.Routes()
	// The frontend is the catch-all: more specific /api/* and /healthz
	// routes win, everything else serves the React app (SPA fallback).
	mux.Handle("GET /", frontendHandler())
	httpSrv := &http.Server{
		Addr:         ":" + port,
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 15 * time.Second,
	}
	go func() {
		<-ctx.Done()
		shCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = httpSrv.Shutdown(shCtx)
	}()

	log.Printf("newsfeed: listening on :%s (%d articles seeded)", port, st.Count())
	if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server: %v", err)
	}
}
