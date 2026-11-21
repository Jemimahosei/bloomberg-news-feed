export interface Article {
    author: string;
    title: string;
    body: string;
    image_url: string;
    url: string;
    publish_date: Date;
}

export interface Quote {
    symbol: string;
    name: string | null;
    price: number | null;
    previous_close: number | null;
    change: number | null;
    change_percent: number | null;
    day_high: number | null;
    day_low: number | null;
    volume: number | null;
    as_of: string | null;
    error: string | null;
}
