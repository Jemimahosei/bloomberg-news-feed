import NewsCard from "@/components/NewsCard";
import NewsFeed, { ArticleItem } from "@/components/NewsFeed";
import { useState, useEffect, useMemo } from "react";

import { Article } from "@/utils/types";

import FeaturedNewsCard from "@/components/FeaturedNews";

function matchesQuery(article: Article, query: string): boolean {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const haystack = `${article.title} ${article.body} ${article.author}`.toLowerCase();
    return haystack.includes(q);
}

export default function News() {
    const [articles, setArticles] = useState<Article[]>([]);
    const [featuredArticle, setFeaturedArticle] = useState<Article | null>(null);
    const [query, setQuery] = useState("");

    useEffect(() => {
        const fetchData = async () => {
            const articlesResponse = await fetch('/api/news/get-newsfeed', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            const featuredArticleResponse = await fetch('/api/news/get-featured-article', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });


            setArticles(await articlesResponse.json());
            setFeaturedArticle(await featuredArticleResponse.json());
        }
        fetchData();
    }, [])

    // Search filters every article by keyword across title, body, and
    // author. While a search is active the featured slot shows the first
    // match, and the grid and sidebar show the same filtered list; with
    // no search everything is exactly as before.
    const searching = query.trim().length > 0;
    const filtered: ArticleItem[] = useMemo(() => {
        return articles
            .map((article, index) => ({ article, index }))
            .filter(({ article }) => matchesQuery(article, query));
    }, [articles, query]);

    const featuredIndex = featuredArticle
        ? articles.findIndex((a) => a.url === featuredArticle.url)
        : -1;
    const shownFeatured = searching ? (filtered[0]?.article ?? null) : featuredArticle;
    const shownFeaturedIndex = searching
        ? (filtered[0]?.index ?? -1)
        : featuredIndex;
    const sidebarItems = filtered.slice(-6);

    return (
        <div>
            <div className="grid grid-cols-4 space-x-2 space-y-2 pt-2">
                <div className="col-span-4 lg:col-span-3">
                    <form
                        className="flex flex-wrap gap-2 pb-4"
                        role="search"
                        onSubmit={(e) => e.preventDefault()}
                    >
                        <input
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Search articles…"
                            aria-label="Search articles"
                            className="border border-slate-300 rounded px-3 py-2 min-w-0 flex-1"
                        />
                        {searching && (
                            <button
                                type="button"
                                onClick={() => setQuery("")}
                                className="border border-slate-300 rounded px-4 py-2"
                            >
                                Clear
                            </button>
                        )}
                    </form>
                    {searching && (
                        <p className="pb-2 text-sm text-body">
                            {filtered.length === 1
                                ? "1 article matching"
                                : `${filtered.length} articles matching`}{" "}
                            &ldquo;{query.trim()}&rdquo;
                        </p>
                    )}
                    <h2 className="featured-news-heading">Featured News</h2>
                    {shownFeatured ? (
                        <FeaturedNewsCard
                            article={shownFeatured}
                            index={shownFeaturedIndex >= 0 ? shownFeaturedIndex : undefined}
                        />
                    ) : searching ? (
                        <p className="text-body pb-4">
                            No articles match &ldquo;{query.trim()}&rdquo;.{" "}
                            <button type="button" onClick={() => setQuery("")} className="underline">
                                Clear search
                            </button>
                        </p>
                    ) : (
                        <div className="featured-news-card" aria-busy="true">
                            <div className="featured-news-img-div">
                                <div className="featured-news-img animate-pulse bg-slate-200" />
                            </div>
                            <div className="featured-news-info">
                                <p className="text-body">Loading featured story…</p>
                            </div>
                        </div>
                    )}
                    <NewsFeed items={filtered} />
                </div>
                <div className="hidden lg:block col-span-1 overflow-hidden border-l border-slate-300">
                    <div className="flex flex-col gap-4 divide-y divide-slate-300 space-x-2">
                    {
                        sidebarItems.map(({ article, index }) => (
                            <NewsCard
                                key={`${article.url}_${index}`}
                                article={article}
                                index={index}
                            />
                        ))
                    }
                    </div>
                </div>
            </div>
        </div>
    );
}
