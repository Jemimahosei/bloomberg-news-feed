// Package store is the in-memory article store. It is safe for concurrent
// use by the ingestion goroutine and the HTTP handlers.
package store

import (
	"sort"
	"strings"
	"sync"
	"time"

	"newsfeed/internal/model"
)

// Store keeps articles keyed by ID.
type Store struct {
	mu        sync.RWMutex
	articles  map[string]model.Article
	updatedAt time.Time
}

// New returns an empty Store.
func New() *Store {
	return &Store{articles: map[string]model.Article{}}
}

// Upsert inserts or replaces articles, returning how many were written.
func (s *Store) Upsert(arts []model.Article) int {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, a := range arts {
		s.articles[a.ID] = a
	}
	if len(arts) > 0 {
		s.updatedAt = time.Now().UTC()
	}
	return len(arts)
}

// LastUpdated returns when articles were last stored (zero if never).
func (s *Store) LastUpdated() time.Time {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.updatedAt
}

// Count returns the number of stored articles.
func (s *Store) Count() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.articles)
}

// sorted returns all articles newest-first.
func (s *Store) sorted() []model.Article {
	out := make([]model.Article, 0, len(s.articles))
	for _, a := range s.articles {
		out = append(out, a)
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].PublishedAt.After(out[j].PublishedAt)
	})
	return out
}

// List returns newest-first articles filtered by category and/or source.
// Empty filters match everything. limit <= 0 means no limit.
func (s *Store) List(category, source string, limit int) []model.Article {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var out []model.Article
	for _, a := range s.sorted() {
		if category != "" && !strings.EqualFold(a.Category, category) {
			continue
		}
		if source != "" && !strings.EqualFold(a.Source, source) {
			continue
		}
		out = append(out, a)
		if limit > 0 && len(out) >= limit {
			break
		}
	}
	if out == nil {
		out = []model.Article{}
	}
	return out
}

// Search returns newest-first articles whose title or description contains
// the query (case-insensitive). limit <= 0 means no limit.
func (s *Store) Search(query string, limit int) []model.Article {
	s.mu.RLock()
	defer s.mu.RUnlock()
	q := strings.ToLower(query)
	var out []model.Article
	for _, a := range s.sorted() {
		if strings.Contains(strings.ToLower(a.Title), q) ||
			strings.Contains(strings.ToLower(a.Description), q) {
			out = append(out, a)
			if limit > 0 && len(out) >= limit {
				break
			}
		}
	}
	if out == nil {
		out = []model.Article{}
	}
	return out
}

// Get returns one article by ID.
func (s *Store) Get(id string) (model.Article, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	a, ok := s.articles[id]
	return a, ok
}

// SearchTicker returns newest-first articles that mention a ticker symbol
// (e.g. AAPL) in the title or description. Matching is token-based, so
// "AAPL" matches "AAPL", "$AAPL" and "(AAPL)" but not "AAPLX".
// limit <= 0 means no limit.
func (s *Store) SearchTicker(symbol string, limit int) []model.Article {
	s.mu.RLock()
	defer s.mu.RUnlock()
	sym := strings.ToUpper(strings.TrimSpace(strings.TrimPrefix(symbol, "$")))
	if sym == "" {
		return []model.Article{}
	}
	var out []model.Article
	for _, a := range s.sorted() {
		if mentionsTicker(a.Title, sym) || mentionsTicker(a.Description, sym) {
			out = append(out, a)
			if limit > 0 && len(out) >= limit {
				break
			}
		}
	}
	if out == nil {
		out = []model.Article{}
	}
	return out
}

// mentionsTicker reports whether symbol appears as a standalone token in
// text. Text is upper-cased and every character that is not a letter,
// digit or "$" becomes a separator, so "(AAPL)" and "$AAPL" both yield
// the token AAPL.
func mentionsTicker(text, symbol string) bool {
	var b strings.Builder
	for _, r := range strings.ToUpper(text) {
		if (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '$' {
			b.WriteRune(r)
		} else {
			b.WriteRune(' ')
		}
	}
	for _, tok := range strings.Fields(b.String()) {
		if tok == symbol || tok == "$"+symbol {
			return true
		}
	}
	return false
}

// Categories returns the distinct categories present, sorted.
func (s *Store) Categories() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	seen := map[string]bool{}
	var out []string
	for _, a := range s.articles {
		if !seen[a.Category] {
			seen[a.Category] = true
			out = append(out, a.Category)
		}
	}
	sort.Strings(out)
	return out
}

// Sources returns the distinct article sources present, sorted.
func (s *Store) Sources() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	seen := map[string]bool{}
	var out []string
	for _, a := range s.articles {
		if !seen[a.Source] {
			seen[a.Source] = true
			out = append(out, a.Source)
		}
	}
	sort.Strings(out)
	return out
}
