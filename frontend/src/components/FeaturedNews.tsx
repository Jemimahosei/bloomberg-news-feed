import type { Article } from '../api'
import { formatDateTime, timeAgo } from '../api'
import ArticleImage from './ArticleImage'

function categoryLabel(c: string): string {
  return c.charAt(0).toUpperCase() + c.slice(1)
}

/**
 * Workshop Part 1: ONE featured news article at the top of the page —
 * the article's title, its image, and a portion of the body truncated
 * to fit nicely in the section.
 */
export default function FeaturedNews({ article }: { article: Article }) {
  return (
    <section className="featured" aria-label="Featured news">
      <p className="section-label">Featured News</p>
      <article className="featured-card">
        <ArticleImage article={article} className="featured-image" />
        <div className="featured-body">
          <div className="headline-top">
            <span className="category-tag">{categoryLabel(article.category)}</span>
            <span className="headline-source">{article.source}</span>
            <span className="headline-time">{timeAgo(article.published_at)}</span>
          </div>
          <h2>{article.title}</h2>
          {article.description && (
            <p className="featured-text">{article.description}</p>
          )}
          <p className="detail-date">{formatDateTime(article.published_at)}</p>
          <a
            className="read-full"
            href={article.url}
            target="_blank"
            rel="noreferrer"
          >
            Read the full article on {article.source} ↗
          </a>
        </div>
      </article>
    </section>
  )
}
