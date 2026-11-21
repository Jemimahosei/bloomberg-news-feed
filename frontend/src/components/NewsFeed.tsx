import React from 'react';
import { Article } from '@/utils/types';
import NewsCard from './NewsCard';

export interface ArticleItem {
    article: Article;
    // Position in the full newsfeed list; the article page lives at /news/{index}.
    index: number;
}

interface NewsFeedProps {
    items: ArticleItem[];
}

function NewsFeed({ items }: NewsFeedProps ) {
    return (
        <div className="stories-container">
            <div className="stories-grid">
                {items.map(({ article, index }) => (
                    <NewsCard
                        key={`${article.url}_${index}`}
                        article={article}
                        index={index}
                    />
                ))}
            </div>
        </div>
    );
};

export default NewsFeed;
