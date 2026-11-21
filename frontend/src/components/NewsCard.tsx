import Link from "next/link";
import { useState } from "react";
import { Article } from "@/utils/types";

interface NewsCardProps {
    article: Article;
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

function NewsCard({ article }: NewsCardProps) {
    const [imgFailed, setImgFailed] = useState(false);
    const showImage = Boolean(article.image_url) && !imgFailed;

    return (
        <div className="news-card">
            <div className="news-info">
                <div className="news-img-div min-h-[3rem] w-full">
                    {showImage ? (
                        <img
                            src={article.image_url}
                            alt={article.title}
                            className="news-img"
                            onError={() => setImgFailed(true)}
                        />
                    ) : (
                        <div className="news-img news-fallback" role="img" aria-label={article.title}>
                            <span className="news-fallback-initial">{sourceInitial(article)}</span>
                        </div>
                    )}
                </div>
                <div className="pt-4 w-full min-w-0">
                    <h2 className="story-title">{article.title}</h2>
                    <p className="story-summary">{article.body}</p>
                    {article.author && <span className="story-author">By {article.author}</span>}
                    {article.url &&
                        <span className="story-author" >
                            <Link className="origin-link" href={article.url} target="_blank">View Story</Link>
                        </span>
                    }
                </div>
            </div>
        </div>
    );
}

export default NewsCard;
