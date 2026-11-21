import { HistoryPoint } from "@/utils/types";

interface StockChartProps {
    points: HistoryPoint[];
    label: string;
}

function formatShortDate(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

// Plain SVG line chart — no chart library. Points are plotted in order;
// the line is green when the last close is at or above the first, red
// when it is below. Only real data points are drawn.
export default function StockChart({ points, label }: StockChartProps) {
    if (points.length === 0) return null;

    const width = 640;
    const height = 220;
    const padLeft = 56;
    const padRight = 12;
    const padTop = 12;
    const padBottom = 28;
    const values = points.map((p) => p.close);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const innerWidth = width - padLeft - padRight;
    const innerHeight = height - padTop - padBottom;
    const x = (i: number) =>
        padLeft + (points.length === 1 ? innerWidth / 2 : (i / (points.length - 1)) * innerWidth);
    const y = (v: number) => padTop + (1 - (v - min) / span) * innerHeight;
    const line = points
        .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.close).toFixed(1)}`)
        .join(" ");
    const area = `${line} L${x(points.length - 1).toFixed(1)},${(padTop + innerHeight).toFixed(1)} L${x(0).toFixed(1)},${(padTop + innerHeight).toFixed(1)} Z`;
    const up = points[points.length - 1].close >= points[0].close;
    const color = up ? "#15803d" : "#dc2626";
    const first = points[0];
    const last = points[points.length - 1];

    return (
        <div className="stock-chart">
            <svg
                viewBox={`0 0 ${width} ${height}`}
                className="w-full h-auto"
                role="img"
                aria-label={`Price chart, ${label}, ${formatShortDate(first.date)} to ${formatShortDate(last.date)}`}
            >
                <path d={area} fill={color} opacity={0.08} />
                <path d={line} fill="none" stroke={color} strokeWidth={2} />
                <circle cx={x(points.length - 1)} cy={y(last.close)} r={4} fill={color} />
                <text x={padLeft - 8} y={y(max) + 4} textAnchor="end" className="stock-chart-label">
                    {max.toFixed(2)}
                </text>
                <text x={padLeft - 8} y={y(min) + 4} textAnchor="end" className="stock-chart-label">
                    {min.toFixed(2)}
                </text>
                <text x={padLeft} y={height - 6} className="stock-chart-label">
                    {formatShortDate(first.date)}
                </text>
                <text x={width - padRight} y={height - 6} textAnchor="end" className="stock-chart-label">
                    {formatShortDate(last.date)}
                </text>
            </svg>
            <p className="stock-chart-range">
                {label} · {formatShortDate(first.date)} – {formatShortDate(last.date)}
            </p>
        </div>
    );
}
