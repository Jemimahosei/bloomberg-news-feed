// Package feed fetches public RSS feeds, normalizes their items into
// model.Article values, and keeps the store fresh on a schedule. It uses
// only the standard library: no API keys and no third-party dependencies.
package feed

import (
	"context"
	"crypto/sha1"
	"encoding/hex"
	"encoding/xml"
	"fmt"
	"html"
	"io"
	"net/http"
	"regexp"
	"strings"
	"time"

	"newsfeed/internal/model"
)

// Source is one RSS feed to ingest. Category is assigned per feed so the
// API can filter by it without depending on each publisher's own taxonomy.
type Source struct {
	Name     string
	URL      string
	Category string
}

// Sources are free, public RSS feeds that need no key or account.
// Market feeds were verified reachable (HTTP 200, valid RSS) in Nov 2026;
// Yahoo Finance RSS and Reuters business RSS were not (404 / 401), so
// they are intentionally not listed.
var Sources = []Source{
	{Name: "MarketWatch", URL: "https://feeds.marketwatch.com/marketwatch/topstories/", Category: "markets"},
	{Name: "CNBC Markets", URL: "https://www.cnbc.com/id/10001147/device/rss/rss.html", Category: "markets"},
	{Name: "Investing.com", URL: "https://www.investing.com/rss/news.rss", Category: "markets"},
	{Name: "CNBC", URL: "https://www.cnbc.com/id/100003114/device/rss/rss.html", Category: "business"},
	{Name: "BBC Business", URL: "https://feeds.bbci.co.uk/news/business/rss.xml", Category: "business"},
	{Name: "The Guardian Business", URL: "https://www.theguardian.com/business/rss", Category: "business"},
	{Name: "BBC News", URL: "https://feeds.bbci.co.uk/news/rss.xml", Category: "general"},
	{Name: "NPR", URL: "https://feeds.npr.org/1001/rss.xml", Category: "general"},
	{Name: "The Guardian", URL: "https://www.theguardian.com/world/rss", Category: "world"},
	{Name: "Hacker News", URL: "https://news.ycombinator.com/rss", Category: "technology"},
	{Name: "Ars Technica", URL: "https://feeds.arstechnica.com/arstechnica/index", Category: "technology"},
}

// rssFeed mirrors the subset of RSS 2.0 we need.
type rssFeed struct {
	Channel struct {
		Items []rssItem `xml:"item"`
	} `xml:"channel"`
}

type mediaRef struct {
	URL    string `xml:"url,attr"`
	Medium string `xml:"medium,attr"`
	Type   string `xml:"type,attr"`
}

type rssItem struct {
	Title          textContent `xml:"title"`
	Link           textContent `xml:"link"`
	Description    textContent `xml:"description"`
	PubDate        textContent `xml:"pubDate"`
	GUID           textContent `xml:"guid"`
	Enclosure      mediaRef    `xml:"enclosure"`
	MediaContent   []mediaRef  `xml:"content"`
	MediaThumbnail []mediaRef  `xml:"thumbnail"`
}

// normalizeImageURL keeps only usable http(s) image URLs. Protocol-
// relative URLs get an https: prefix; anything else is dropped so a
// malformed feed value can never become a broken or invented image.
func normalizeImageURL(u string) string {
	u = strings.TrimSpace(u)
	if strings.HasPrefix(u, "//") {
		return "https:" + u
	}
	if strings.HasPrefix(u, "http://") || strings.HasPrefix(u, "https://") {
		return u
	}
	return ""
}

// pickImage returns the best feed-provided image URL for an item:
// media:content marked as an image first, then any media:content,
// then media:thumbnail, then an image enclosure. It only ever returns
// a URL the feed itself supplied — it never fetches or invents one.
func pickImage(it rssItem) string {
	for _, m := range it.MediaContent {
		if m.Medium == "image" || strings.HasPrefix(strings.ToLower(m.Type), "image/") {
			if u := normalizeImageURL(m.URL); u != "" {
				return u
			}
		}
	}
	for _, m := range it.MediaContent {
		if u := normalizeImageURL(m.URL); u != "" {
			return u
		}
	}
	for _, m := range it.MediaThumbnail {
		if u := normalizeImageURL(m.URL); u != "" {
			return u
		}
	}
	// Enclosures are often audio (podcasts); only accept image ones
	// (or an undeclared type, which image enclosures sometimes omit).
	if t := strings.ToLower(strings.TrimSpace(it.Enclosure.Type)); t == "" || strings.HasPrefix(t, "image/") {
		return normalizeImageURL(it.Enclosure.URL)
	}
	return ""
}

// textContent collects every character-data chunk inside an element,
// including text nested in child markup. Plain string fields drop nested
// text, but real RSS descriptions routinely contain raw HTML tags, so
// this keeps e.g. "<p>Stocks rose <b>sharply</b></p>" intact for stripping.
type textContent string

func (t *textContent) UnmarshalXML(d *xml.Decoder, start xml.StartElement) error {
	var sb strings.Builder
	depth := 1
	for depth > 0 {
		tok, err := d.Token()
		if err != nil {
			return err
		}
		switch tok := tok.(type) {
		case xml.CharData:
			sb.Write([]byte(tok))
		case xml.StartElement:
			depth++
		case xml.EndElement:
			depth--
		}
	}
	*t = textContent(sb.String())
	return nil
}

var tagRe = regexp.MustCompile(`<[^>]*>`)

// stripHTML removes markup from RSS descriptions and unescapes entities.
func stripHTML(s string) string {
	s = tagRe.ReplaceAllString(s, " ")
	s = html.UnescapeString(s)
	return strings.Join(strings.Fields(s), " ")
}

// parsePubDate tries the date layouts publishers actually emit.
func parsePubDate(s string) time.Time {
	s = strings.TrimSpace(s)
	if s == "" {
		return time.Now().UTC()
	}
	layouts := []string{
		time.RFC1123Z,
		time.RFC1123,
		time.RFC822Z,
		time.RFC822,
		time.RFC3339,
		"Mon, 2 Jan 2006 15:04:05 MST",
		"Mon, 2 Jan 2006 15:04:05 -0700",
		"2006-01-02 15:04:05 -0700",
		"2006-01-02 15:04:05", // Investing.com emits a bare local time
	}
	for _, l := range layouts {
		if t, err := time.Parse(l, s); err == nil {
			return t.UTC()
		}
	}
	return time.Now().UTC()
}

// articleID is a stable, deterministic ID derived from the article URL.
func articleID(url string) string {
	sum := sha1.Sum([]byte(url))
	return hex.EncodeToString(sum[:])[:16]
}

// parseRSS turns raw feed XML into articles for one source.
func parseRSS(data []byte, src Source) ([]model.Article, error) {
	var f rssFeed
	if err := xml.Unmarshal(data, &f); err != nil {
		return nil, fmt.Errorf("parse rss from %s: %w", src.Name, err)
	}
	var out []model.Article
	for _, it := range f.Channel.Items {
		link := strings.TrimSpace(string(it.Link))
		if link == "" {
			link = strings.TrimSpace(string(it.GUID))
		}
		if link == "" || strings.TrimSpace(string(it.Title)) == "" {
			continue
		}
		out = append(out, model.Article{
			ID:          articleID(link),
			Title:       strings.TrimSpace(string(it.Title)),
			Description: stripHTML(string(it.Description)),
			URL:         link,
			Source:      src.Name,
			Category:    src.Category,
			PublishedAt: parsePubDate(string(it.PubDate)),
			ImageURL:    pickImage(it),
		})
	}
	return out, nil
}

// fetchSource downloads and parses a single feed.
func fetchSource(ctx context.Context, client *http.Client, src Source) ([]model.Article, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, src.URL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "newsfeed/1.0 (+demo project)")
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("feed %s returned %s", src.Name, resp.Status)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if err != nil {
		return nil, err
	}
	return parseRSS(body, src)
}

// FetchAll pulls every configured feed concurrently and returns the
// deduplicated articles (first-seen wins per URL).
func FetchAll(ctx context.Context) ([]model.Article, error) {
	client := &http.Client{Timeout: 20 * time.Second}
	type result struct {
		articles []model.Article
		err      error
	}
	ch := make(chan result, len(Sources))
	for _, src := range Sources {
		go func(s Source) {
			arts, err := fetchSource(ctx, client, s)
			ch <- result{articles: arts, err: err}
		}(src)
	}
	seen := map[string]bool{}
	var all []model.Article
	var errs []string
	for range Sources {
		r := <-ch
		if r.err != nil {
			errs = append(errs, r.err.Error())
			continue
		}
		for _, a := range r.articles {
			if seen[a.URL] {
				continue
			}
			seen[a.URL] = true
			all = append(all, a)
		}
	}
	if len(all) == 0 && len(errs) > 0 {
		return nil, fmt.Errorf("all feeds failed: %s", strings.Join(errs, "; "))
	}
	return all, nil
}
