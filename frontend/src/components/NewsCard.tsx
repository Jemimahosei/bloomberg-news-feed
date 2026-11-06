import type { Article } from '../api'
import { timeAgo } from '../api'
import ArticleImage from './ArticleImage'

function categoryLabel(c: string): string {
  return c.charAt(0).toUpperCase() + c.slice(1)
}

/**
 * Workshop Part 2: a reusable news card for general stories — the
 * article's title, its image, and a truncated version of the body.
 * Reusable so it populates every story in the feed.
 */
export default function NewsCard({ article }: { article: Article }) {
  return (
    <article className="news-card">
      <a
        href={article.url}
        target="_blank"
        rel="noreferrer"
        className="news-card-link"
        aria-label={article.title}
      >
        <ArticleImage article={article} className="news-card-image" />
        <div className="news-card-body">
          <div className="headline-top">
            <span className="category-tag">{categoryLabel(article.category)}</span>
            <span className="headline-source">{article.source}</span>
            <span className="headline-time">{timeAgo(article.published_at)}</span>
          </div>
          <h3>{article.title}</h3>
          {article.description && (
            <p className="news-card-text">{article.description}</p>
          )}
        </div>
      </a>
    </article>
  )
}
