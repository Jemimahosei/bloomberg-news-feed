import Link from "next/link";
import { Article } from "@/utils/types";

interface NewsCardProps {
    article: Article;
}


function NewsCard({ article }: NewsCardProps) {
    return (
        <div className="news-card">
            <div className="news-info">
                <div className="news-img-div min-h-[3rem] w-full">
                    <img
                        src={article.image_url}
                        alt={article.title}
                        className="news-img"
                        onError={(e) => { e.currentTarget.style.display = "none"; }}
                    />
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
