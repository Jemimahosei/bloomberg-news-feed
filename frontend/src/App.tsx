import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchArticle,
  fetchCategories,
  fetchHeadlines,
  fetchHealth,
  fetchSources,
  formatDateTime,
  searchArticles,
  timeAgo,
} from './api'
import type { Article } from './api'

const TICKERS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'JPM', 'AMD', 'NFLX']

function categoryLabel(c: string): string {
  return c.charAt(0).toUpperCase() + c.slice(1)
}

export default function App() {
  const [articles, setArticles] = useState<Article[]>([])
  const [selected, setSelected] = useState<Article | null>(null)
  const [categories, setCategories] = useState<string[]>([])
  const [sources, setSources] = useState<string[]>([])
  const [category, setCategory] = useState('')
  const [ticker, setTicker] = useState('')
  const [source, setSource] = useState('')
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [totalCount, setTotalCount] = useState<number | null>(null)
  const [now, setNow] = useState(() => new Date())
  const [mobileDetail, setMobileDetail] = useState(false)
  const requestId = useRef(0)

  // Live clock in the header.
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30000)
    return () => clearInterval(t)
  }, [])

  // Debounce the search box.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query.trim()), 350)
    return () => clearTimeout(t)
  }, [query])

  // Filter metadata + feed freshness, once on mount.
  useEffect(() => {
    fetchCategories().then(setCategories).catch(() => undefined)
    fetchSources().then(setSources).catch(() => undefined)
    fetchHealth()
      .then((h) => {
        setTotalCount(h.articles)
        setUpdatedAt(h.updated_at ?? null)
      })
      .catch(() => undefined)
  }, [])

  const load = useCallback(async () => {
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const res = debouncedQuery
        ? await searchArticles(debouncedQuery)
        : await fetchHeadlines({ category, source, ticker })
      if (id !== requestId.current) return
      setArticles(res.data)
      setSelected((prev) => {
        if (prev) {
          const stillThere = res.data.find((a) => a.id === prev.id)
          if (stillThere) return stillThere
        }
        return res.data[0] ?? null
      })
    } catch (e) {
      if (id !== requestId.current) return
      setError(e instanceof Error ? e.message : 'Could not load headlines.')
      setArticles([])
      setSelected(null)
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [category, source, ticker, debouncedQuery])

  useEffect(() => {
    void load()
  }, [load])

  const openArticle = useCallback(async (a: Article) => {
    setSelected(a)
    setMobileDetail(true)
    try {
      const full = await fetchArticle(a.id)
      setSelected((prev) => (prev && prev.id === a.id ? full : prev))
    } catch {
      // The list item already has everything needed to render.
    }
  }, [])

  const clearFilters = () => {
    setCategory('')
    setTicker('')
    setSource('')
    setQuery('')
  }

  const allSample = useMemo(
    () => articles.length > 0 && articles.every((a) => a.source === 'Sample Wire'),
    [articles],
  )
  const filtersActive = category !== '' || ticker !== '' || source !== '' || debouncedQuery !== ''

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

      <div className="controls">
        <div className="tabs" role="tablist" aria-label="Category">
          <button
            className={category === '' ? 'tab active' : 'tab'}
            onClick={() => setCategory('')}
          >
            All
          </button>
          {categories.map((c) => (
            <button
              key={c}
              className={category === c ? 'tab active' : 'tab'}
              onClick={() => setCategory(c)}
            >
              {categoryLabel(c)}
            </button>
          ))}
        </div>
        <div className="search-row">
          <input
            className="search"
            type="search"
            placeholder="Search headlines…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search headlines"
          />
          <select
            className="source-select"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            aria-label="Filter by source"
          >
            <option value="">All sources</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="tickers" aria-label="Filter by ticker">
          <span className="tickers-label">Tickers</span>
          {TICKERS.map((t) => (
            <button
              key={t}
              className={ticker === t ? 'ticker active' : 'ticker'}
              onClick={() => setTicker(ticker === t ? '' : t)}
            >
              {t}
            </button>
          ))}
          {filtersActive && (
            <button className="clear-filters" onClick={clearFilters}>
              Clear filters
            </button>
          )}
        </div>
      </div>

      {allSample && (
        <div className="notice">
          Live news feeds are unreachable right now, so this page is showing bundled
          sample headlines. They are labeled “Sample Wire” and will be replaced by live
          stories as soon as the feeds respond.
        </div>
      )}
      {debouncedQuery && (
        <div className="search-note">
          Searching all headlines for “{debouncedQuery}”
        </div>
      )}

      <main className="panes">
        <section
          className={`list-pane ${mobileDetail ? 'hidden-mobile' : ''}`}
          aria-label="Headlines"
        >
          {loading && <div className="status">Loading headlines…</div>}
          {!loading && error && (
            <div className="status error">
              Couldn’t reach the news service ({error}). Check the connection and try
              again.
            </div>
          )}
          {!loading && !error && articles.length === 0 && (
            <div className="status">
              No headlines match this filter right now. Try a different category, ticker
              or search.
            </div>
          )}
          {!loading &&
            !error &&
            articles.map((a) => (
              <article
                key={a.id}
                className={`headline ${selected?.id === a.id ? 'selected' : ''}`}
                onClick={() => void openArticle(a)}
              >
                <div className="headline-top">
                  <span className="category-tag">{categoryLabel(a.category)}</span>
                  <span className="headline-source">{a.source}</span>
                  <span className="headline-time">{timeAgo(a.published_at)}</span>
                </div>
                <h2>{a.title}</h2>
                {a.description && <p>{a.description}</p>}
              </article>
            ))}
        </section>

        <section
          className={`detail-pane ${mobileDetail ? 'visible-mobile' : ''}`}
          aria-label="Article detail"
        >
          {selected ? (
            <>
              <button
                className="back-button"
                onClick={() => setMobileDetail(false)}
              >
                ← Back to headlines
              </button>
              <div className="detail-top">
                <span className="category-tag">{categoryLabel(selected.category)}</span>
                <span className="headline-source">{selected.source}</span>
              </div>
              <h1>{selected.title}</h1>
              <p className="detail-date">{formatDateTime(selected.published_at)}</p>
              {selected.description && <p className="detail-body">{selected.description}</p>}
              <a
                className="read-full"
                href={selected.url}
                target="_blank"
                rel="noreferrer"
              >
                Read the full article on {selected.source} ↗
              </a>
            </>
          ) : (
            !loading && (
              <div className="status">Select a headline to read it here.</div>
            )
          )}
        </section>
      </main>

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
