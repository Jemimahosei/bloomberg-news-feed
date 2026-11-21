import { useState, useEffect } from "react";
import { Quote } from "@/utils/types";

// Slim ticker tape under the nav: live watchlist quotes in the
// Bloomberg style (black strip, symbol + price + % change). It renders
// nothing while loading or when the feed fails — never a broken strip.
export default function TickerTape() {
    const [quotes, setQuotes] = useState<Quote[]>([]);

    useEffect(() => {
        fetch('/api/news/get-stocks', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        })
            .then((response) => response.json())
            .then((data: Quote[]) => {
                setQuotes(data.filter((q) => q.price !== null && !q.error).slice(0, 8));
            })
            .catch(() => {
                setQuotes([]);
            });
    }, []);

    if (quotes.length === 0) return null;

    return (
        <div className="ticker-tape" aria-label="Market quotes">
            {quotes.map((quote) => {
                const change = quote.change_percent;
                const changeClass = change === null || change === undefined || change === 0
                    ? ""
                    : change > 0 ? "ticker-tape-up" : "ticker-tape-down";
                const sign = change !== null && change !== undefined && change > 0 ? "+" : "";
                return (
                    <span key={quote.symbol} className="ticker-tape-item">
                        <span className="ticker-tape-symbol">{quote.symbol}</span>
                        <span>{quote.price?.toFixed(2)}</span>
                        {change !== null && change !== undefined && (
                            <span className={changeClass}>{`${sign}${change.toFixed(2)}%`}</span>
                        )}
                    </span>
                );
            })}
        </div>
    );
}
