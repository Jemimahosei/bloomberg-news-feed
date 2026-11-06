package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"newsfeed/internal/model"
	"newsfeed/internal/store"
)

// stubCache is a map-backed Cache for handler tests.
type stubCache struct {
	mu   sync.Mutex
	data map[string][]byte
}

func (c *stubCache) Get(_ context.Context, key string) ([]byte, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	v, ok := c.data[key]
	return v, ok
}

func (c *stubCache) Set(_ context.Context, key string, value []byte, _ time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.data == nil {
		c.data = map[string][]byte{}
	}
	c.data[key] = value
}

func testServer() *Server {
	st := store.New()
	st.Upsert([]model.Article{
		{ID: "a1", Title: "Inflation cools", Description: "prices ease", Source: "BBC News", Category: "business", URL: "https://example.com/a1", PublishedAt: time.Date(2026, 10, 26, 9, 0, 0, 0, time.UTC)},
		{ID: "a2", Title: "Chip stocks rally", Description: "semiconductor gains", Source: "BBC News", Category: "technology", URL: "https://example.com/a2", PublishedAt: time.Date(2026, 10, 25, 9, 0, 0, 0, time.UTC)},
	})
	return &Server{Store: st, Cache: &stubCache{}, TTL: time.Minute}
}

func get(t *testing.T, h http.Handler, path string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestHeadlinesAndFilters(t *testing.T) {
	srv := testServer()
	h := srv.Routes()

	rec := get(t, h, "/api/headlines")
	if rec.Code != http.StatusOK {
		t.Fatalf("headlines status = %d", rec.Code)
	}
	var body struct {
		Data  []model.Article `json:"data"`
		Count int             `json:"count"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if body.Count != 2 || body.Data[0].ID != "a1" {
		t.Fatalf("headlines = %+v", body)
	}

	rec = get(t, h, "/api/headlines?category=technology")
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body.Count != 1 || body.Data[0].ID != "a2" {
		t.Fatalf("category filter = %+v", body)
	}

	rec = get(t, h, "/api/headlines?limit=1")
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body.Count != 1 {
		t.Fatalf("limit = %+v", body)
	}
}

func TestSearchAndDetail(t *testing.T) {
	srv := testServer()
	h := srv.Routes()

	if rec := get(t, h, "/api/search"); rec.Code != http.StatusBadRequest {
		t.Fatalf("search without q = %d, want 400", rec.Code)
	}
	rec := get(t, h, "/api/search?q=INFLATION")
	var body struct {
		Data  []model.Article `json:"data"`
		Count int             `json:"count"`
	}
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body.Count != 1 {
		t.Fatalf("search = %+v", body)
	}

	rec = get(t, h, "/api/articles/a1")
	if rec.Code != http.StatusOK {
		t.Fatalf("detail = %d", rec.Code)
	}
	var one struct {
		Data model.Article `json:"data"`
	}
	_ = json.Unmarshal(rec.Body.Bytes(), &one)
	if one.Data.Title != "Inflation cools" {
		t.Fatalf("detail title = %q", one.Data.Title)
	}
	if rec := get(t, h, "/api/articles/nope"); rec.Code != http.StatusNotFound {
		t.Fatalf("missing detail = %d, want 404", rec.Code)
	}
}

func TestCacheHeaders(t *testing.T) {
	srv := testServer()
	h := srv.Routes()
	first := get(t, h, "/api/headlines")
	if first.Header().Get("X-Cache") != "MISS" {
		t.Fatalf("first request X-Cache = %q, want MISS", first.Header().Get("X-Cache"))
	}
	second := get(t, h, "/api/headlines")
	if second.Header().Get("X-Cache") != "HIT" {
		t.Fatalf("second request X-Cache = %q, want HIT", second.Header().Get("X-Cache"))
	}
	if first.Body.String() != second.Body.String() {
		t.Fatalf("cached body differs from fresh body")
	}
}

func TestHealthAndCategories(t *testing.T) {
	srv := testServer()
	h := srv.Routes()
	rec := get(t, h, "/healthz")
	if rec.Code != http.StatusOK {
		t.Fatalf("healthz = %d", rec.Code)
	}
	rec = get(t, h, "/api/categories")
	var body struct {
		Data  []string `json:"data"`
		Count int      `json:"count"`
	}
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body.Count != 2 {
		t.Fatalf("categories = %+v", body)
	}
}

func TestTickerFilterAndSources(t *testing.T) {
	srv := testServer()
	// Add a ticker-bearing article to the shared fixture store.
	srv.Store.Upsert([]model.Article{
		{ID: "a3", Title: "AAPL jumps on earnings", Description: "Apple beat estimates", Source: "CNBC", Category: "markets", URL: "https://example.com/a3", PublishedAt: time.Date(2026, 10, 26, 10, 0, 0, 0, time.UTC)},
	})
	h := srv.Routes()

	rec := get(t, h, "/api/headlines?ticker=aapl")
	var body struct {
		Data  []model.Article `json:"data"`
		Count int             `json:"count"`
	}
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body.Count != 1 || body.Data[0].ID != "a3" {
		t.Fatalf("ticker filter = %+v", body)
	}
	rec = get(t, h, "/api/headlines?ticker=ZZZZ")
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body.Count != 0 {
		t.Fatalf("unknown ticker = %+v", body)
	}
	// Ticker combined with a category that does not match must be empty.
	rec = get(t, h, "/api/headlines?ticker=aapl&category=technology")
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body.Count != 0 {
		t.Fatalf("ticker+category mismatch = %+v", body)
	}

	rec = get(t, h, "/api/sources")
	var srcs struct {
		Data  []string `json:"data"`
		Count int      `json:"count"`
	}
	_ = json.Unmarshal(rec.Body.Bytes(), &srcs)
	if srcs.Count != 2 || srcs.Data[0] != "BBC News" || srcs.Data[1] != "CNBC" {
		t.Fatalf("sources = %+v", srcs)
	}
}
