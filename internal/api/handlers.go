// Package api exposes the news service over HTTP. Every list/detail
// response is cached in Redis (when available) with a TTL; the X-Cache
// header reports HIT or MISS so the caching layer is visible in demos.
package api

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"newsfeed/internal/cache"
	"newsfeed/internal/model"
	"newsfeed/internal/store"
)

// Server bundles the dependencies handlers need.
type Server struct {
	Store *store.Store
	Cache cache.Cache
	TTL   time.Duration
}

func (s *Server) ttl() time.Duration {
	if s.TTL > 0 {
		return s.TTL
	}
	return 60 * time.Second
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func parseLimit(r *http.Request, def, max int) int {
	n, err := strconv.Atoi(r.URL.Query().Get("limit"))
	if err != nil || n <= 0 {
		return def
	}
	if n > max {
		return max
	}
	return n
}

// cached runs fn to build a response, serving the Redis copy when present.
// The cache key must already encode every parameter that affects the body.
func (s *Server) cached(w http.ResponseWriter, r *http.Request, key string, fn func() (any, int)) {
	ctx := r.Context()
	if data, ok := s.Cache.Get(ctx, key); ok {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Cache", "HIT")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(data)
		return
	}
	body, status := fn()
	if status != http.StatusOK {
		writeJSON(w, status, body)
		return
	}
	data, err := json.Marshal(body)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "encode response"})
		return
	}
	s.Cache.Set(ctx, key, data, s.ttl())
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "MISS")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

type listResponse struct {
	Data  []model.Article `json:"data"`
	Count int             `json:"count"`
}

// Headlines returns the latest articles, optionally filtered by category,
// source and/or ticker: GET /api/headlines?category=markets&ticker=AAPL&limit=20
func (s *Server) Headlines(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	category, source, ticker := q.Get("category"), q.Get("source"), q.Get("ticker")
	limit := parseLimit(r, 20, 100)
	key := "headlines:category=" + category + "&source=" + source + "&ticker=" + ticker + "&limit=" + strconv.Itoa(limit)
	s.cached(w, r, key, func() (any, int) {
		var arts []model.Article
		if ticker != "" {
			arts = s.Store.SearchTicker(ticker, 0)
			// Apply the category/source filters on top of the ticker match.
			filtered := arts[:0]
			for _, a := range arts {
				if category != "" && !strings.EqualFold(a.Category, category) {
					continue
				}
				if source != "" && !strings.EqualFold(a.Source, source) {
					continue
				}
				filtered = append(filtered, a)
			}
			arts = filtered
			if len(arts) > limit {
				arts = arts[:limit]
			}
		} else {
			arts = s.Store.List(category, source, limit)
		}
		return listResponse{Data: arts, Count: len(arts)}, http.StatusOK
	})
}

// Search returns articles matching q in title or description:
// GET /api/search?q=inflation&limit=20
func (s *Server) Search(w http.ResponseWriter, r *http.Request) {
	q := strings.TrimSpace(r.URL.Query().Get("q"))
	limit := parseLimit(r, 20, 100)
	key := "search:q=" + q + "&limit=" + strconv.Itoa(limit)
	s.cached(w, r, key, func() (any, int) {
		if q == "" {
			return map[string]string{"error": "missing required query parameter: q"}, http.StatusBadRequest
		}
		arts := s.Store.Search(q, limit)
		return listResponse{Data: arts, Count: len(arts)}, http.StatusOK
	})
}

// ArticleDetail returns one article: GET /api/articles/{id}
func (s *Server) ArticleDetail(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	key := "article:id=" + id
	s.cached(w, r, key, func() (any, int) {
		a, ok := s.Store.Get(id)
		if !ok {
			return map[string]string{"error": "article not found"}, http.StatusNotFound
		}
		return map[string]any{"data": a}, http.StatusOK
	})
}

// FeaturedArticle returns the single featured article (the newest one),
// per the workshop spec: GET /api/news/get-featured-article
func (s *Server) FeaturedArticle(w http.ResponseWriter, r *http.Request) {
	s.cached(w, r, "news:featured", func() (any, int) {
		a, ok := s.Store.Featured()
		if !ok {
			return map[string]string{"error": "no articles available"}, http.StatusNotFound
		}
		return map[string]any{"data": a}, http.StatusOK
	})
}

// Newsfeed returns the article list for the workshop's News Feed grid:
// GET /api/news/get-newsfeed?limit=50
func (s *Server) Newsfeed(w http.ResponseWriter, r *http.Request) {
	limit := parseLimit(r, 50, 100)
	key := "news:newsfeed&limit=" + strconv.Itoa(limit)
	s.cached(w, r, key, func() (any, int) {
		arts := s.Store.List("", "", limit)
		return listResponse{Data: arts, Count: len(arts)}, http.StatusOK
	})
}

// Categories lists the distinct categories currently present.
func (s *Server) Categories(w http.ResponseWriter, r *http.Request) {
	cats := s.Store.Categories()
	if cats == nil {
		cats = []string{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": cats, "count": len(cats)})
}

// Sources lists the distinct article sources currently present.
func (s *Server) Sources(w http.ResponseWriter, r *http.Request) {
	srcs := s.Store.Sources()
	if srcs == nil {
		srcs = []string{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": srcs, "count": len(srcs)})
}

// Health reports liveness plus the current article count and last ingest.
func (s *Server) Health(w http.ResponseWriter, r *http.Request) {
	updated := s.Store.LastUpdated()
	out := map[string]any{
		"status":   "ok",
		"articles": s.Store.Count(),
	}
	if !updated.IsZero() {
		out["updated_at"] = updated.Format(time.RFC3339)
	}
	writeJSON(w, http.StatusOK, out)
}

// Routes wires all endpoints onto a ServeMux (Go 1.22+ patterns). It
// returns the mux so the caller can mount additional handlers (e.g. the
// static frontend) on the same server.
func (s *Server) Routes() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.Health)
	mux.HandleFunc("GET /api/headlines", s.Headlines)
	mux.HandleFunc("GET /api/search", s.Search)
	mux.HandleFunc("GET /api/articles/{id}", s.ArticleDetail)
	mux.HandleFunc("GET /api/news/get-featured-article", s.FeaturedArticle)
	mux.HandleFunc("GET /api/news/get-newsfeed", s.Newsfeed)
	mux.HandleFunc("GET /api/categories", s.Categories)
	mux.HandleFunc("GET /api/sources", s.Sources)
	return mux
}

// Ensure the context import stays referenced for future middleware use.
var _ = context.Background
