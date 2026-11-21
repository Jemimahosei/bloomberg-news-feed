import { useState, useEffect, useCallback, FormEvent } from "react";

import { Quote, HistoryResponse } from "@/utils/types";
import StockChart from "@/components/StockChart";

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

function QuoteRow({ quote, selected, onSelect }: { quote: Quote; selected: boolean; onSelect: () => void }) {
    return (
        <tr
            className={`border-b border-slate-300 cursor-pointer hover:bg-slate-50 ${selected ? "bg-slate-100" : ""}`}
            onClick={onSelect}
            title={`Show ${quote.symbol} price chart`}
        >
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
    const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
    const [history, setHistory] = useState<HistoryResponse | null>(null);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [historyError, setHistoryError] = useState<string | null>(null);

    // Plain quote fetch used by the initial load and the auto-refresh.
    // It only updates the quotes; loading and search state are untouched
    // so a background refresh never flashes the page.
    const fetchQuotes = useCallback(async (): Promise<Quote[] | null> => {
        const response = await fetch('/api/news/get-stocks', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    }, []);

    const loadWatchlist = async () => {
        setLoading(true);
        setLoadError(null);
        setSearchResult(null);
        setSearchMessage(null);
        try {
            const data = await fetchQuotes();
            setQuotes(data ?? []);
        } catch {
            setLoadError("Stock data is unavailable right now. Please try again later.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadWatchlist();
    }, []);

    // Auto-refresh: re-fetch the quotes every 60 seconds so the page
    // stays current (and the "as of" line moves) without a manual
    // reload. Skipped while the tab is hidden. The backend caches
    // quotes for 120 seconds, so a refresh inside that window is cheap.
    useEffect(() => {
        const timer = setInterval(() => {
            if (document.hidden) return;
            fetchQuotes()
                .then((data) => {
                    if (data) setQuotes(data);
                })
                .catch(() => {
                    // Keep showing the last good quotes; the next
                    // refresh tries again.
                });
        }, 60000);
        return () => clearInterval(timer);
    }, [fetchQuotes]);

    // Default the chart to the first watchlist ticker once quotes load.
    useEffect(() => {
        if (selectedSymbol === null && quotes.length > 0) {
            setSelectedSymbol(quotes[0].symbol);
        }
    }, [quotes, selectedSymbol]);

    // Load the price history whenever the selected ticker changes.
    useEffect(() => {
        if (!selectedSymbol) return;
        setHistoryLoading(true);
        setHistoryError(null);
        setHistory(null);
        fetch(`/api/news/get-history?symbol=${encodeURIComponent(selectedSymbol)}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        })
            .then((response) => response.json())
            .then((data: HistoryResponse) => {
                if (data.error === "not_found") {
                    setHistoryError(`No price history found for ${selectedSymbol}.`);
                } else if (data.error === "unavailable" || !data.points || data.points.length === 0) {
                    setHistoryError("Price history is unavailable right now.");
                } else {
                    setHistory(data);
                }
            })
            .catch(() => {
                setHistoryError("Price history is unavailable right now.");
            })
            .finally(() => {
                setHistoryLoading(false);
            });
    }, [selectedSymbol]);

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
    // The whole feed failed when every watchlist quote came back with an
    // error. Individual missing values still show as dashes; this banner
    // says the feed itself is down instead of leaving silent dashes.
    const feedFailed =
        !searchResult && !loading && !loadError && quotes.length > 0 && quotes.every((q) => q.error);

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
                    {feedFailed && (
                        <p className="pb-4 font-bold text-red-600">
                            Quotes unavailable right now — try again shortly.
                        </p>
                    )}
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
                                    <QuoteRow
                                        key={quote.symbol}
                                        quote={quote}
                                        selected={quote.symbol === selectedSymbol}
                                        onSelect={() => setSelectedSymbol(quote.symbol)}
                                    />
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <p className="pt-2 text-sm text-body">Select a row to see its price chart.</p>
                    {selectedSymbol && (
                        <div className="pt-4">
                            <h3 className="stock-chart-heading">{selectedSymbol} — Price history</h3>
                            {historyLoading ? (
                                <p className="text-body" aria-busy="true">Loading chart…</p>
                            ) : historyError ? (
                                <p className="text-body">{historyError}</p>
                            ) : history ? (
                                <StockChart points={history.points} label={history.label} />
                            ) : null}
                        </div>
                    )}
                    <p className="pt-4 text-sm text-body">
                        Quotes from Yahoo Finance and Nasdaq. Prices show the last close when markets are closed.
                    </p>
                </>
            )}
        </div>
    );
}
