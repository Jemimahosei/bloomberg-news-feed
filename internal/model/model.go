// Package model defines the article type shared by the feed ingester,
// the store, and the HTTP API.
package model

import "time"

// Article is a single news item, normalized from an RSS entry or from the
// bundled sample dataset.
type Article struct {
	ID          string    `json:"id"`
	Title       string    `json:"title"`
	Description string    `json:"description"`
	URL         string    `json:"url"`
	Source      string    `json:"source"`
	Category    string    `json:"category"`
	PublishedAt time.Time `json:"published_at"`
	ImageURL    string    `json:"image_url,omitempty"`
}
