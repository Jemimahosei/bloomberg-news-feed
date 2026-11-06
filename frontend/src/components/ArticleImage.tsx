import { useState } from 'react'
import type { Article } from '../api'

function categoryLabel(c: string): string {
  return c.charAt(0).toUpperCase() + c.slice(1)
}

/**
 * Article image: the feed-provided image when one exists and loads,
 * otherwise a designed fallback tile (source initial + category). Only
 * URLs the RSS feed itself supplied are ever rendered — no stock photos,
 * no scraped images, no invented URLs. A feed image that fails to load
 * falls back to the tile as well.
 */
export default function ArticleImage({
  article,
  className,
}: {
  article: Article
  className?: string
}) {
  const [failed, setFailed] = useState(false)
  const initial = (article.source || '?').trim().charAt(0).toUpperCase()

  if (!article.image_url || failed) {
    return (
      <div
        className={`image-fallback ${className ?? ''}`}
        role="img"
        aria-label={`No image provided by ${article.source}`}
      >
        <span className="image-fallback-initial">{initial}</span>
        <span className="image-fallback-category">
          {categoryLabel(article.category)}
        </span>
        <span className="image-fallback-note">No image from feed</span>
      </div>
    )
  }
  return (
    <img
      className={`article-image ${className ?? ''}`}
      src={article.image_url}
      alt={article.title}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}
