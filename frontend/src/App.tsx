import { useEffect, useState } from 'react'
import {
  fetchFeaturedArticle,
  fetchHealth,
  fetchNewsfeed,
  timeAgo,
} from './api'
import type { Article } from './api'
import FeaturedNews from './components/FeaturedNews'
import NewsFeed from './components/NewsFeed'

/**
 * Page structure follows the Bloomberg Tech Lab on Campus workshop spec
 * verbatim: header → Featured News (one featured article, top of page)
 * → News Feed grid (bottom of page) → footer. No category tabs, no
 * ticker chips, no source filter, no search box — none of those are in
 * the workshop instructions.
 */
export default function App() {
  const [featured, setFeatured] = useState<Article | null>(null)
  const [articles, setArticles] = useState<Article[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [totalCount, setTotalCount] = useState<number | null>(null)
  const [now, setNow] = useState(() => new Date())

  // Live clock in the header.
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30000)
    return () => clearInterval(t)
  }, [])

  // Feed freshness, once on mount.
  useEffect(() => {
    fetchHealth()
      .then((h) => {
        setTotalCount(h.articles)
        setUpdatedAt(h.updated_at ?? null)
      })
      .catch(() => undefined)
  }, [])

  // Workshop Part 4: featured article + news feed, both from the API.
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [f, feed] = await Promise.all([
          fetchFeaturedArticle(),
          fetchNewsfeed(50),
        ])
        if (cancelled) return
        setFeatured(f)
        // The featured story sits at the top of the page; keep it out of
        // the grid below so the same article is not shown twice.
        setArticles(feed.data.filter((a) => a.id !== f.id))
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Could not load headlines.')
        setFeatured(null)
        setArticles([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const allSample =
    featured !== null &&
    featured.source === 'Sample Wire' &&
    articles.every((a) => a.source === 'Sample Wire')

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">NEWSFEED</span>
          <span className="brand-sub">Market News Terminal</span>
        </div>
        <div className="topbar-meta">
          <span className="clock">
            {now.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}
          </span>
          {totalCount !== null && <span className="meta-item">{totalCount} headlines</span>}
          {updatedAt && <span className="meta-item">Updated {timeAgo(updatedAt)}</span>}
        </div>
      </header>

      {allSample && (
        <div className="notice">
          Live news feeds are unreachable right now, so this page is showing bundled
          sample headlines. They are labeled “Sample Wire” and will be replaced by live
          stories as soon as the feeds respond.
        </div>
      )}

      {loading && <div className="status">Loading headlines…</div>}
      {!loading && error && (
        <div className="status error">
          Couldn’t reach the news service ({error}). Check the connection and try
          again.
        </div>
      )}
      {!loading && !error && featured && (
        <>
          <FeaturedNews article={featured} />
          <NewsFeed articles={articles} />
        </>
      )}
      {!loading && !error && !featured && (
        <div className="status">No headlines right now. Check back soon.</div>
      )}

      <footer className="footer">
        <p>
          Headlines come from free public RSS feeds — MarketWatch, CNBC,
          Investing.com, BBC News, The Guardian, NPR, Hacker News and Ars
          Technica. No accounts, no API keys.
        </p>
        <p>
          Built by Jemimah Osei as a portfolio project, following the Bloomberg
          Tech Lab on Campus at Cornell (March 2025). Not affiliated with
          Bloomberg L.P.
        </p>
      </footer>
    </div>
  )
}
