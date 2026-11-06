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

const imageRSS = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
<title>Test Feed</title>
<item>
<title>Media content wins</title>
<link>https://example.com/mc</link>
<description>Has both media:content and media:thumbnail.</description>
<pubDate>Mon, 26 Oct 2026 09:00:00 GMT</pubDate>
<media:content url="https://example.com/full.jpg" medium="image"/>
<media:thumbnail url="https://example.com/thumb.jpg"/>
</item>
<item>
<title>Thumbnail fallback</title>
<link>https://example.com/th</link>
<description>Thumbnail only; audio enclosure must be ignored.</description>
<pubDate>Mon, 26 Oct 2026 08:00:00 GMT</pubDate>
<media:thumbnail url="https://example.com/thumb2.jpg"/>
<enclosure url="https://example.com/audio.mp3" type="audio/mpeg"/>
</item>
<item>
<title>Image enclosure</title>
<link>https://example.com/enc</link>
<description>Image enclosure, no media tags.</description>
<pubDate>Mon, 26 Oct 2026 07:00:00 GMT</pubDate>
<enclosure url="https://example.com/pic.png" type="image/png"/>
</item>
<item>
<title>Audio only</title>
<link>https://example.com/aud</link>
<description>Audio enclosure and nothing else: no image.</description>
<pubDate>Mon, 26 Oct 2026 06:00:00 GMT</pubDate>
<enclosure url="https://example.com/audio.mp3" type="audio/mpeg"/>
</item>
<item>
<title>Protocol relative</title>
<link>https://example.com/pr</link>
<description>Protocol-relative media URL gets an https: prefix.</description>
<pubDate>Mon, 26 Oct 2026 05:00:00 GMT</pubDate>
<media:content url="//example.com/proto.jpg" medium="image"/>
</item>
</channel>
</rss>`

// TestParseRSSImages checks image extraction priority: media:content
// (image) > media:thumbnail > image enclosure, and that non-image
// enclosures never produce an image URL.
func TestParseRSSImages(t *testing.T) {
	src := Source{Name: "Test", URL: "https://example.com/rss", Category: "business"}
	arts, err := parseRSS([]byte(imageRSS), src)
	if err != nil {
		t.Fatalf("parseRSS: %v", err)
	}
	if len(arts) != 5 {
		t.Fatalf("expected 5 articles, got %d", len(arts))
	}
	want := map[string]string{
		"Media content wins":  "https://example.com/full.jpg",
		"Thumbnail fallback":  "https://example.com/thumb2.jpg",
		"Image enclosure":     "https://example.com/pic.png",
		"Audio only":          "",
		"Protocol relative":   "https://example.com/proto.jpg",
	}
	for _, a := range arts {
		if want[a.Title] != a.ImageURL {
			t.Errorf("%q image = %q, want %q", a.Title, a.ImageURL, want[a.Title])
		}
	}
}
