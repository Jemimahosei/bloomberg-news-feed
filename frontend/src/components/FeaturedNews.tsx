import Link from "next/link";
import { useState } from "react";
import { Article } from "@/utils/types";

interface NewsCardProps {
    article: Article;
    // Position in the full newsfeed list; the article page lives at /news/{index}.
    index?: number;
}

function sourceInitial(article: Article): string {
    try {
        if (article.url) {
            const host = new URL(article.url).hostname.replace(/^www\./, "");
            if (host) return host.charAt(0).toUpperCase();
        }
    } catch {
        // Fall through to the title initial.
    }
    return (article.title || "?").trim().charAt(0).toUpperCase() || "?";
}

function FeaturedNewsCard({ article, index }: NewsCardProps) {
    const [imgFailed, setImgFailed] = useState(false);
    const showImage = Boolean(article.image_url) && !imgFailed;

    return (
        <div className="featured-news-card">
            <div className="featured-news-img-div">
                {showImage ? (
                    <img
                        src={article.image_url}
                        alt={article.title}
                        className="featured-news-img"
                        onError={() => setImgFailed(true)}
                    />
                ) : (
                    <div className="featured-news-img featured-fallback" role="img" aria-label={article.title}>
                        <span className="featured-fallback-initial">{sourceInitial(article)}</span>
                    </div>
                )}
            </div>
            <div className="featured-news-info">
                <h2 className="featured-story-title">
                    {index !== undefined ? (
                        <Link href={`/news/${index}`} className="featured-title-link">{article.title}</Link>
                    ) : (
                        article.title
                    )}
                </h2>
                <p className="featured-story-summary">{article.body}</p>
                {article.author && <span className="featured-story-author">By {article.author}</span>}
                {article.url &&
                    <span className="featured-story-author" >
                        Via <Link className="origin-link" href={article.url} target="_blank">{article.url}</Link>
                    </span>
                }
            </div>
        </div>
    );
}

export default FeaturedNewsCard;
