import { useState, useEffect, FormEvent } from "react";

import { Quote } from "@/utils/types";

const TICKER_RE = /^[A-Z0-9.\-]{1,12}$/;

function formatPrice(value: number | null): string {
    return value === null || value === undefined ? "—" : value.toFixed(2);
}

function formatSigned(value: number | null, suffix = ""): string {
    if (value === null || value === undefined) return "—";
    const sign = value > 0 ? "+" : "";
    return `${sign}${value.toFixed(2)}${suffix}`;
}

function formatVolume(value: number | null): string {
    return value === null || value === undefined ? "—" : value.toLocaleString();
}

function formatAsOf(asOf: string | null): string {
    if (!asOf) return "";
    return new Date(asOf).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function changeClass(value: number | null): string {
    if (value === null || value === undefined || value === 0) return "text-body";
    return value > 0 ? "text-green-600" : "text-red-600";
}

function QuoteRow({ quote }: { quote: Quote }) {
    return (
        <tr className="border-b border-slate-300">
            <td className="py-3 pr-4">
                <div className="font-bold text-title">{quote.symbol}</div>
                {quote.name && <div className="text-sm text-body">{quote.name}</div>}
            </td>
            <td className="py-3 pr-4 text-right font-bold text-title">{formatPrice(quote.price)}</td>
            <td className={`py-3 pr-4 text-right ${changeClass(quote.change)}`}>{formatSigned(quote.change)}</td>
            <td className={`py-3 pr-4 text-right ${changeClass(quote.change_percent)}`}>{formatSigned(quote.change_percent, "%")}</td>
            <td className="py-3 pr-4 text-right hidden md:table-cell">{formatPrice(quote.day_high)}</td>
            <td className="py-3 pr-4 text-right hidden md:table-cell">{formatPrice(quote.day_low)}</td>
            <td className="py-3 text-right hidden lg:table-cell">{formatVolume(quote.volume)}</td>
        </tr>
    );
}

export default function Stocks() {
    const [quotes, setQuotes] = useState<Quote[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [searchInput, setSearchInput] = useState("");
    const [searching, setSearching] = useState(false);
    const [searchMessage, setSearchMessage] = useState<string | null>(null);
    const [searchResult, setSearchResult] = useState<Quote | null>(null);

    const loadWatchlist = async () => {
        setLoading(true);
        setLoadError(null);
        setSearchResult(null);
        setSearchMessage(null);
        try {
            const response = await fetch('/api/news/get-stocks', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            setQuotes(data);
        } catch {
            setLoadError("Stock data is unavailable right now. Please try again later.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadWatchlist();
    }, []);

    const onSearch = async (event: FormEvent) => {
        event.preventDefault();
        const symbol = searchInput.trim().toUpperCase();
        if (!TICKER_RE.test(symbol)) {
            setSearchMessage("Enter a valid ticker symbol (letters, numbers, dots and dashes only).");
            setSearchResult(null);
            return;
        }
        setSearching(true);
        setSearchMessage(null);
        setSearchResult(null);
        try {
            const response = await fetch(`/api/news/get-stocks?symbols=${encodeURIComponent(symbol)}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            const quote: Quote | undefined = data[0];
            if (!quote || quote.error === "not_found") {
                setSearchMessage(`No quote found for ${symbol}. Check the ticker and try again.`);
            } else if (quote.error === "unavailable") {
                setSearchMessage(`A quote for ${symbol} is unavailable right now. Please try again later.`);
            } else {
                setSearchResult(quote);
            }
        } catch {
            setSearchMessage("Stock data is unavailable right now. Please try again later.");
        } finally {
            setSearching(false);
        }
    };

    const displayed = searchResult ? [searchResult] : quotes;
    const asOf = displayed.map((q) => q.as_of).find(Boolean) ?? null;

    return (
        <div>
            <h2 className="featured-news-heading">Stocks</h2>

            <form onSubmit={onSearch} className="flex flex-wrap gap-2 pb-4">
                <input
                    type="text"
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    placeholder="Look up a ticker, e.g. AAPL"
                    aria-label="Ticker symbol"
                    className="border border-slate-300 rounded px-3 py-2 min-w-0 flex-1"
                />
                <button
                    type="submit"
                    disabled={searching}
                    className="bg-primary text-white font-bold rounded px-4 py-2 disabled:opacity-50"
                >
                    {searching ? "Searching…" : "Search"}
                </button>
                {searchResult && (
                    <button type="button" onClick={loadWatchlist} className="border border-slate-300 rounded px-4 py-2">
                        Back to watchlist
                    </button>
                )}
            </form>

            {searchMessage && <p className="pb-4 text-body">{searchMessage}</p>}

            {loading ? (
                <p className="text-body" aria-busy="true">Loading quotes…</p>
            ) : loadError ? (
                <p className="text-body">{loadError}</p>
            ) : displayed.length === 0 ? (
                <p className="text-body">No quotes to show right now.</p>
            ) : (
                <>
                    {asOf && <p className="pb-2 text-sm text-body">Quotes as of {formatAsOf(asOf)}</p>}
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead>
                                <tr className="border-b border-slate-300 text-body">
                                    <th className="py-2 pr-4">Symbol</th>
                                    <th className="py-2 pr-4 text-right">Price</th>
                                    <th className="py-2 pr-4 text-right">Change</th>
                                    <th className="py-2 pr-4 text-right">% Change</th>
                                    <th className="py-2 pr-4 text-right hidden md:table-cell">Day High</th>
                                    <th className="py-2 pr-4 text-right hidden md:table-cell">Day Low</th>
                                    <th className="py-2 text-right hidden lg:table-cell">Volume</th>
                                </tr>
                            </thead>
                            <tbody>
                                {displayed.map((quote) => (
                                    <QuoteRow key={quote.symbol} quote={quote} />
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <p className="pt-4 text-sm text-body">
                        Quotes from Yahoo Finance. Prices show the last close when markets are closed.
                    </p>
                </>
            )}
        </div>
    );
}
