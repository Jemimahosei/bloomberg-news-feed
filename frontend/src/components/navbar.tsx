// components/Navbar.js
import Link from 'next/link';
import { useState } from 'react';

export default function Navbar() {
    return (
        <nav>
            <div className="nav-div">
                <Link href={'/'}>
                    <span id="navbar-home-span-wrapper">
                        <span id="navbar-home-span">The Tech Lab Times</span>
                    </span>
                </Link>
                <div className="navbar-navigation-wrapper" id="navbar-default">
                    <div className="navbar-list-wrapper">
                        <ul className="navbar-list">
                            <li>
                                <Link href='/news'><span className="menu-item" aria-current="page">News</span></Link>
                            </li>
                            <li>
                                <Link href='/stocks'><span className="menu-item">Stocks</span></Link>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
        </nav>
    );
}
