package feed

import (
	"context"
	_ "embed"
	"encoding/json"
	"log"
	"time"

	"newsfeed/internal/model"
	"newsfeed/internal/store"
)

//go:embed sample.json
var sampleData []byte

// loadSample unmarshals the bundled demo dataset. It is only used when
// live ingestion yields nothing, so the API always has something to show.
func loadSample() ([]model.Article, error) {
	var arts []model.Article
	if err := json.Unmarshal(sampleData, &arts); err != nil {
		return nil, err
	}
	return arts, nil
}

// IngestOnce fetches all feeds and upserts the results. It returns how many
// new-or-updated articles were stored.
func IngestOnce(ctx context.Context, st *store.Store) (int, error) {
	arts, err := FetchAll(ctx)
	if err != nil {
		return 0, err
	}
	return st.Upsert(arts), nil
}

// EnsureSeeded runs one ingestion pass. If live ingestion produces nothing
// (no network, feeds down), it falls back to the bundled sample dataset so
// the API still demonstrates end-to-end.
func EnsureSeeded(ctx context.Context, st *store.Store) {
	n, err := IngestOnce(ctx, st)
	if err != nil {
		log.Printf("ingest: live fetch failed (%v); trying bundled sample data", err)
	}
	if n == 0 {
		arts, serr := loadSample()
		if serr != nil {
			log.Printf("ingest: sample data failed: %v", serr)
			return
		}
		st.Upsert(arts)
		log.Printf("ingest: seeded %d sample articles (live feeds unavailable)", len(arts))
		return
	}
	log.Printf("ingest: stored %d articles from live feeds", n)
}

// StartScheduler re-runs ingestion on an interval. Failures are logged and
// the previous articles keep serving; a failed tick never empties the store.
func StartScheduler(ctx context.Context, st *store.Store, interval time.Duration) {
	t := time.NewTicker(interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			n, err := IngestOnce(ctx, st)
			if err != nil {
				log.Printf("ingest: scheduled fetch failed: %v (keeping %d articles)", err, st.Count())
				continue
			}
			log.Printf("ingest: scheduled refresh stored %d articles", n)
		}
	}
}
