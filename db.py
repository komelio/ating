# -*- coding: utf-8 -*-
"""V3.1 Dashboard — SQLite database module."""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.expanduser("~/dashboard/data/market.db")
DATA_DIR = os.path.expanduser("~/dashboard/data")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS market_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL,
            price REAL,
            change_pct REAL,
            volume REAL,
            high REAL,
            low REAL,
            open REAL,
            prev_close REAL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS stock_price (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            price REAL,
            change_pct REAL,
            change_amt REAL,
            volume REAL,
            turnover REAL,
            high REAL,
            low REAL,
            open REAL,
            prev_close REAL,
            pe REAL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS portfolio_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_asset REAL,
            total_profit REAL,
            total_profit_pct REAL,
            cash REAL,
            cash_cow_pct REAL,
            growth_pct REAL,
            frontier_pct REAL,
            snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ai_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            source TEXT,
            url TEXT,
            category TEXT,
            published_at TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_market_fetched ON market_index(fetched_at);
        CREATE INDEX IF NOT EXISTS idx_stock_fetched ON stock_price(fetched_at);
        CREATE INDEX IF NOT EXISTS idx_news_fetched ON ai_news(fetched_at);
    """)
    conn.commit()
    conn.close()


def export_all_json():
    """Export latest data to JSON files for frontend."""
    conn = get_db()
    os.makedirs(DATA_DIR, exist_ok=True)

    # Market index — latest snapshot
    cur = conn.execute("""
        SELECT DISTINCT name, code, MAX(price) as price, MAX(change_pct) as change_pct,
               MAX(volume) as volume, MAX(high) as high, MAX(low) as low,
               MAX(open) as open, MAX(prev_close) as prev_close
        FROM market_index
        WHERE fetched_at > datetime('now', '-1 day')
        GROUP BY code
    """)
    market = [dict(r) for r in cur.fetchall()]
    with open(os.path.join(DATA_DIR, "market.json"), "w") as f:
        json.dump({"updated": datetime.now().isoformat(), "indices": market}, f, ensure_ascii=False)

    # Stock prices — latest per stock
    cur = conn.execute("""
        SELECT code, name, price, change_pct, change_amt, volume, turnover, pe,
               high, low, open, prev_close, fetched_at
        FROM stock_price sp1
        WHERE fetched_at = (SELECT MAX(fetched_at) FROM stock_price sp2 WHERE sp2.code = sp1.code)
        ORDER BY code
    """)
    stocks = [dict(r) for r in cur.fetchall()]
    with open(os.path.join(DATA_DIR, "stocks.json"), "w") as f:
        json.dump({"updated": datetime.now().isoformat(), "stocks": stocks}, f, ensure_ascii=False)

    # Portfolio — from sim-portfolio.json
    try:
        with open(os.path.expanduser("~/.hermes/portfolio/sim-portfolio.json")) as f:
            portfolio = json.load(f)
    except Exception:
        portfolio = {}
    with open(os.path.join(DATA_DIR, "portfolio.json"), "w") as f:
        json.dump(portfolio, f, ensure_ascii=False)

    # Latest news
    cur = conn.execute("""
        SELECT title, source, url, category, published_at
        FROM ai_news
        ORDER BY fetched_at DESC
        LIMIT 30
    """)
    news = [dict(r) for r in cur.fetchall()]
    with open(os.path.join(DATA_DIR, "news.json"), "w") as f:
        json.dump({"updated": datetime.now().isoformat(), "news": news}, f, ensure_ascii=False)

    # Historical market data (last 30 entries)
    cur = conn.execute("""
        SELECT fetched_at, name, price, change_pct
        FROM market_index
        ORDER BY fetched_at DESC
        LIMIT 90
    """)
    history_rows = [dict(r) for r in cur.fetchall()]
    with open(os.path.join(DATA_DIR, "history.json"), "w") as f:
        json.dump({"updated": datetime.now().isoformat(), "history": history_rows}, f, ensure_ascii=False)

    conn.close()
    return True


if __name__ == "__main__":
    init_db()
    print("Database initialized:", DB_PATH)