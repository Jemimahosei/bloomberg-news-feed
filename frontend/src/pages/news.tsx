import NewsCard from "@/components/NewsCard";
import NewsFeed from "@/components/NewsFeed";
import { useState, useEffect } from "react";

import { Article } from "@/utils/types";

import FeaturedNewsCard from "@/components/FeaturedNews";

export default function News() {
    const [articles, setArticles] = useState<Article[]>([]);
    const [featuredArticle, setFeaturedArticle] = useState<Article | null>(null);

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

    return (
        <div>
            <div className="grid grid-cols-4 space-x-2 space-y-2 pt-2">
                <div className="col-span-4 lg:col-span-3">
                    <h2 className="featured-news-heading">Featured News</h2>
                    {featuredArticle ? (
                        <FeaturedNewsCard article={featuredArticle} />
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
                    <NewsFeed articles={articles} />
                </div>
                <div className="hidden lg:block col-span-1 overflow-hidden border-l border-slate-300">
                    <div className="flex flex-col gap-4 divide-y divide-slate-300 space-x-2">
                    {
                        articles.slice(-6).map((article, i) => (
                            <NewsCard
                                key={`${article}_${i}`}
                                article={article}
                            />
                        ))
                    }
                    </div>
                </div>
            </div>
        </div>
    );
}
