import type { Article } from '../api'
import NewsCard from './NewsCard'

/**
 * Workshop Part 3: a News Feed populating a GRID of NewsCards at the
 * bottom of the page, under the Featured News section.
 */
export default function NewsFeed({ articles }: { articles: Article[] }) {
  return (
    <section className="newsfeed-section" aria-label="News feed">
      <p className="section-label">News Feed</p>
      {articles.length === 0 ? (
        <div className="status">No headlines right now. Check back soon.</div>
      ) : (
        <div className="news-grid">
          {articles.map((a) => (
            <NewsCard key={a.id} article={a} />
          ))}
        </div>
      )}
    </section>
  )
}
