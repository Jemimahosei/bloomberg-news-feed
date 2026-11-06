package store

import (
	"testing"
	"time"

	"newsfeed/internal/model"
)

func TestSearchTicker(t *testing.T) {
	st := New()
	now := time.Now().UTC()
	st.Upsert([]model.Article{
		{ID: "t1", Title: "AAPL climbs after earnings beat", Description: "Apple shares rose", Source: "CNBC", Category: "markets", URL: "https://example.com/t1", PublishedAt: now},
		{ID: "t2", Title: "Chip stocks rally", Description: "Investors bought (NVDA) on data-center demand", Source: "CNBC", Category: "markets", URL: "https://example.com/t2", PublishedAt: now.Add(-time.Hour)},
		{ID: "t3", Title: "AAPLX files for a new fund", Description: "unrelated fund news", Source: "BBC News", Category: "business", URL: "https://example.com/t3", PublishedAt: now.Add(-2 * time.Hour)},
		{ID: "t4", Title: "Market roundup", Description: "$MSFT and $AAPL led the Dow", Source: "MarketWatch", Category: "markets", URL: "https://example.com/t4", PublishedAt: now.Add(-3 * time.Hour)},
	})

	got := st.SearchTicker("aapl", 0)
	if len(got) != 2 || got[0].ID != "t1" || got[1].ID != "t4" {
		t.Fatalf("SearchTicker(aapl) = %v, want [t1 t4]", ids(got))
	}
	got = st.SearchTicker("$NVDA", 0)
	if len(got) != 1 || got[0].ID != "t2" {
		t.Fatalf("SearchTicker($NVDA) = %v, want [t2]", ids(got))
	}
	// AAPLX must not match AAPL.
	got = st.SearchTicker("AAPL", 0)
	for _, a := range got {
		if a.ID == "t3" {
			t.Fatalf("SearchTicker(AAPL) wrongly matched AAPLX article t3")
		}
	}
	if got := st.SearchTicker("ZZZZ", 0); len(got) != 0 {
		t.Fatalf("SearchTicker(ZZZZ) = %v, want empty", ids(got))
	}
	if got := st.SearchTicker("", 0); len(got) != 0 {
		t.Fatalf("SearchTicker(\"\") = %v, want empty", ids(got))
	}
}

func ids(arts []model.Article) []string {
	out := make([]string, len(arts))
	for i, a := range arts {
		out[i] = a.ID
	}
	return out
}

func TestSourcesAndLastUpdated(t *testing.T) {
	st := New()
	if !st.LastUpdated().IsZero() {
		t.Fatalf("LastUpdated on empty store should be zero")
	}
	st.Upsert([]model.Article{
		{ID: "s1", Title: "x", Source: "CNBC", Category: "business", URL: "https://example.com/s1", PublishedAt: time.Now().UTC()},
		{ID: "s2", Title: "y", Source: "BBC News", Category: "general", URL: "https://example.com/s2", PublishedAt: time.Now().UTC()},
		{ID: "s3", Title: "z", Source: "CNBC", Category: "business", URL: "https://example.com/s3", PublishedAt: time.Now().UTC()},
	})
	srcs := st.Sources()
	if len(srcs) != 2 || srcs[0] != "BBC News" || srcs[1] != "CNBC" {
		t.Fatalf("Sources() = %v, want [BBC News CNBC]", srcs)
	}
	if st.LastUpdated().IsZero() {
		t.Fatalf("LastUpdated should be set after Upsert")
	}
}
