export interface Article {
  id: string
  title: string
  description: string
  url: string
  source: string
  category: string
  published_at: string
  image_url?: string
}

interface ListResponse {
  data: Article[]
  count: number
}

interface StringsResponse {
  data: string[]
  count: number
}

interface HealthResponse {
  status: string
  articles: number
  updated_at?: string
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`)
  }
  return (await res.json()) as T
}

export interface HeadlineFilters {
  category?: string
  source?: string
  ticker?: string
  limit?: number
}

export function fetchHeadlines(f: HeadlineFilters): Promise<ListResponse> {
  const p = new URLSearchParams()
  if (f.category) p.set('category', f.category)
  if (f.source) p.set('source', f.source)
  if (f.ticker) p.set('ticker', f.ticker)
  p.set('limit', String(f.limit ?? 50))
  return getJSON<ListResponse>(`/api/headlines?${p.toString()}`)
}

export function searchArticles(q: string, limit = 50): Promise<ListResponse> {
  const p = new URLSearchParams({ q, limit: String(limit) })
  return getJSON<ListResponse>(`/api/search?${p.toString()}`)
}

export function fetchArticle(id: string): Promise<Article> {
  return getJSON<{ data: Article }>(`/api/articles/${encodeURIComponent(id)}`).then(
    (r) => r.data,
  )
}

export function fetchCategories(): Promise<string[]> {
  return getJSON<StringsResponse>('/api/categories').then((r) => r.data)
}

export function fetchSources(): Promise<string[]> {
  return getJSON<StringsResponse>('/api/sources').then((r) => r.data)
}

export function fetchHealth(): Promise<HealthResponse> {
  return getJSON<HealthResponse>('/healthz')
}

/** Human-friendly relative time, e.g. "5m ago", "2h ago", "Mar 4". */
export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (secs < 60) return 'just now'
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  if (secs < 86400 * 2) return 'yesterday'
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}
