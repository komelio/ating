CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    code TEXT NOT NULL,
    name TEXT,
    price REAL,
    change_pct REAL,
    volume REAL,
    turnover REAL,
    type TEXT DEFAULT 'stock'  -- stock, index, sector
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    total_assets REAL,
    cash REAL,
    market_value REAL,
    total_pnl REAL,
    total_pnl_pct REAL,
    drawdown_pct REAL
);

CREATE TABLE IF NOT EXISTS holding_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    code TEXT NOT NULL,
    name TEXT,
    shares INTEGER,
    avg_cost REAL,
    current_price REAL,
    market_value REAL,
    pnl REAL,
    pnl_pct REAL
);

CREATE TABLE IF NOT EXISTS trade_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    action TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    shares INTEGER,
    price REAL,
    amount REAL,
    commission REAL DEFAULT 5.0
);

CREATE TABLE IF NOT EXISTS analysis_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    market_state TEXT,
    volume TEXT,
    up_down_ratio TEXT,
    state_reason TEXT,
    pelt_warnings TEXT,  -- JSON array
    decisions TEXT,       -- JSON array
    thoughts TEXT
);

CREATE TABLE IF NOT EXISTS news_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    source TEXT,
    title TEXT,
    url TEXT,
    published_at TEXT,
    UNIQUE(title, source)
);

CREATE INDEX idx_market_time ON market_snapshots(timestamp);
CREATE INDEX idx_market_code ON market_snapshots(code);
CREATE INDEX idx_portfolio_time ON portfolio_snapshots(timestamp);
CREATE INDEX idx_holding_time ON holding_snapshots(timestamp);
CREATE INDEX idx_news_time ON news_cache(timestamp);