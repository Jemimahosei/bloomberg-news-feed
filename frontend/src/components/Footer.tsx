// Small, quiet footer for the links that are not part of the core
// functionality (News and Stocks live in the top nav). Muted and
// centered, so it never competes with the masthead or the nav.
import Link from "next/link";

const links = [
    { label: "Github", href: "https://github.com/Jemimahosei/bloomberg-news-feed" },
    { label: "Documentation", href: "https://bloombergtechlab.github.io/bbit-learning-labs/" },
    { label: "Redis", href: "https://redis.io/docs/" },
    { label: "Stretch Goals", href: "https://bloombergtechlab.github.io/bbit-learning-labs/frontend/" },
];

export default function Footer() {
    return (
        <footer className="mt-8 border-t border-slate-200 py-4 text-center text-xs text-slate-400">
            {links.map((link, i) => (
                <span key={link.href}>
                    {i > 0 && (
                        <span className="mx-2 text-slate-300" aria-hidden="true">·</span>
                    )}
                    <Link href={link.href} target="_blank" className="hover:text-slate-600 hover:underline">
                        {link.label}
                    </Link>
                </span>
            ))}
        </footer>
    );
}
