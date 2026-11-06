package store

import (
	"testing"
	"time"

	"newsfeed/internal/model"
)

func mk(id, title, desc, source, category string, day int) model.Article {
	return model.Article{
		ID: id, Title: title, Description: desc, Source: source, Category: category,
		PublishedAt: time.Date(2026, time.October, day, 10, 0, 0, 0, time.UTC),
		URL:         "https://example.com/" + id,
	}
}

func seedStore() *Store {
	s := New()
	s.Upsert([]model.Article{
		mk("a1", "Inflation cools in October", "prices ease", "BBC News", "business", 26),
		mk("a2", "Chip stocks rally", "semiconductor inflation bets", "BBC News", "technology", 25),
		mk("a3", "Climate talks resume", "funding deal", "The Guardian", "world", 24),
	})
	return s
}

func TestListFiltersAndOrder(t *testing.T) {
	s := seedStore()
	all := s.List("", "", 0)
	if len(all) != 3 || all[0].ID != "a1" || all[2].ID != "a3" {
		t.Fatalf("list order = %v", all)
	}
	biz := s.List("business", "", 0)
	if len(biz) != 1 || biz[0].ID != "a1" {
		t.Errorf("category filter = %v", biz)
	}
	bbc := s.List("", "bbc news", 0) // case-insensitive source match
	if len(bbc) != 2 {
		t.Errorf("source filter = %d", len(bbc))
	}
	lim := s.List("", "", 2)
	if len(lim) != 2 {
		t.Errorf("limit = %d", len(lim))
	}
	if none := s.List("sports", "", 0); len(none) != 0 {
		t.Errorf("unknown category should be empty, got %d", len(none))
	}
}

func TestSearch(t *testing.T) {
	s := seedStore()
	hits := s.Search("INFLATION", 0) // case-insensitive, title + description
	if len(hits) != 2 {
		t.Fatalf("search = %d, want 2", len(hits))
	}
	if none := s.Search("zzz-no-match", 0); len(none) != 0 {
		t.Errorf("no-match search should be empty")
	}
}

func TestGetAndCategories(t *testing.T) {
	s := seedStore()
	if _, ok := s.Get("a2"); !ok {
		t.Errorf("Get(a2) missing")
	}
	if _, ok := s.Get("missing"); ok {
		t.Errorf("Get(missing) should be absent")
	}
	cats := s.Categories()
	if len(cats) != 3 || cats[0] != "business" {
		t.Errorf("categories = %v", cats)
	}
	// Upsert replaces by ID.
	s.Upsert([]model.Article{mk("a1", "Updated title", "", "BBC News", "business", 27)})
	if a, _ := s.Get("a1"); a.Title != "Updated title" {
		t.Errorf("upsert did not replace: %q", a.Title)
	}
	if s.Count() != 3 {
		t.Errorf("count after replace = %d, want 3", s.Count())
	}
}
