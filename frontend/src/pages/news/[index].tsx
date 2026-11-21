import Link from "next/link";
import { useRouter } from "next/router";
import { useState, useEffect } from "react";
import { Article } from "@/utils/types";

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

function formatDate(value: string | Date): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString([], { dateStyle: "long" });
}

// Full article view at /news/{index}, where index is the article's
// position in the newsfeed list (newest first). The dataset is fixed,
// so the index is stable.
export default function ArticlePage() {
    const router = useRouter();
    const { index } = router.query;
    const [article, setArticle] = useState<Article | null>(null);
    const [loaded, setLoaded] = useState(false);
    const [notFound, setNotFound] = useState(false);
    const [imgFailed, setImgFailed] = useState(false);

    useEffect(() => {
        if (!router.isReady) return;
        const raw = Array.isArray(index) ? index[0] : index ?? "";
        const n = parseInt(raw, 10);
        if (Number.isNaN(n)) {
            setNotFound(true);
            setLoaded(true);
            return;
        }
        fetch('/api/news/get-newsfeed', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        })
            .then((response) => response.json())
            .then((data: Article[]) => {
                const found = data[n];
                if (!found) {
                    setNotFound(true);
                } else {
                    setArticle(found);
                }
                setLoaded(true);
            })
            .catch(() => {
                setNotFound(true);
                setLoaded(true);
            });
    }, [router.isReady, index]);

    const showImage = article ? Boolean(article.image_url) && !imgFailed : false;
    const paragraphs = article
        ? article.body.split(/\n+/).map((p) => p.trim()).filter(Boolean)
        : [];

    return (
        <div>
            <p className="pt-2 pb-4">
                <Link href="/news" className="origin-link">&larr; Back to news</Link>
            </p>
            {!loaded ? (
                <p className="text-body" aria-busy="true">Loading article…</p>
            ) : notFound || !article ? (
                <p className="text-body">
                    This article could not be found.{" "}
                    <Link href="/news" className="origin-link">Back to news</Link>
                </p>
            ) : (
                <article className="article-detail">
                    <h1 className="article-detail-title">{article.title}</h1>
                    <p className="article-detail-byline">
                        {article.author && <span>By {article.author}</span>}
                        {article.author && article.publish_date && <span> · </span>}
                        {article.publish_date && <span>{formatDate(article.publish_date)}</span>}
                    </p>
                    <div className="article-detail-img-div">
                        {showImage ? (
                            <img
                                src={article.image_url}
                                alt={article.title}
                                className="article-detail-img"
                                onError={() => setImgFailed(true)}
                            />
                        ) : (
                            <div className="article-detail-img article-detail-fallback" role="img" aria-label={article.title}>
                                <span className="article-detail-fallback-initial">{sourceInitial(article)}</span>
                            </div>
                        )}
                    </div>
                    <div className="article-detail-body">
                        {paragraphs.map((paragraph, i) => (
                            <p key={i}>{paragraph}</p>
                        ))}
                    </div>
                    {article.url && (
                        <p className="article-detail-source">
                            Via <Link className="origin-link" href={article.url} target="_blank">{article.url}</Link>
                        </p>
                    )}
                </article>
            )}
        </div>
    );
}
