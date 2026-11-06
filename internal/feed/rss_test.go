package feed

import (
	"strings"
	"testing"
	"time"
)

const sampleRSS = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Test Feed</title>
<item>
<title>Markets rally on rate hopes</title>
<link>https://example.com/markets-rally</link>
<description><p>Stocks rose <b>sharply</b> after the data.</p></description>
<pubDate>Mon, 26 Oct 2026 09:00:00 GMT</pubDate>
<enclosure url="https://example.com/img.jpg" type="image/jpeg"/>
</item>
<item>
<title>Second story</title>
<link>https://example.com/second</link>
<description>Plain text description.</description>
<pubDate>2026-10-25T18:30:00Z</pubDate>
</item>
<item>
<title></title>
<link>https://example.com/empty-title</link>
<description>Skipped: no title.</description>
</item>
</channel>
</rss>`

func TestParseRSS(t *testing.T) {
	src := Source{Name: "Test", URL: "https://example.com/rss", Category: "business"}
	arts, err := parseRSS([]byte(sampleRSS), src)
	if err != nil {
		t.Fatalf("parseRSS: %v", err)
	}
	if len(arts) != 2 {
		t.Fatalf("expected 2 articles (empty-title item skipped), got %d", len(arts))
	}
	a := arts[0]
	if a.Title != "Markets rally on rate hopes" {
		t.Errorf("title = %q", a.Title)
	}
	if a.Description != "Stocks rose sharply after the data." {
		t.Errorf("description not stripped: %q", a.Description)
	}
	if a.Source != "Test" || a.Category != "business" {
		t.Errorf("source/category = %q/%q", a.Source, a.Category)
	}
	if a.ImageURL != "https://example.com/img.jpg" {
		t.Errorf("image = %q", a.ImageURL)
	}
	if a.ID == "" || len(a.ID) != 16 {
		t.Errorf("id = %q", a.ID)
	}
	// Same URL must always map to the same ID.
	if arts[0].ID != articleID("https://example.com/markets-rally") {
		t.Errorf("id not deterministic")
	}
	// RFC1123 GMT date parsed.
	if a.PublishedAt.Year() != 2026 || a.PublishedAt.Month() != time.October {
		t.Errorf("published = %v", a.PublishedAt)
	}
	// RFC3339 date parsed on second item.
	if arts[1].PublishedAt.Day() != 25 {
		t.Errorf("second published = %v", arts[1].PublishedAt)
	}
}

func TestParsePubDateLayouts(t *testing.T) {
	for _, s := range []string{
		"Mon, 26 Oct 2026 09:00:00 -0000",
		"Mon, 26 Oct 2026 09:00:00 GMT",
		"26 Oct 26 09:00 GMT",
		"2026-10-26T09:00:00Z",
		"Mon, 26 Oct 2026 09:00:00 +0000",
	} {
		if got := parsePubDate(s); got.Year() != 2026 {
			t.Errorf("parsePubDate(%q) = %v", s, got)
		}
	}
}

func TestStripHTML(t *testing.T) {
	got := stripHTML("<p>Hello &amp; <b>world</b></p>")
	if got != "Hello & world" {
		t.Errorf("stripHTML = %q", got)
	}
	if !strings.Contains(stripHTML("a   b"), "a b") {
		t.Errorf("whitespace not collapsed")
	}
}
