# -*- coding: utf-8 -*-
"""V3.1 Dashboard — 数据库模块。SQLite 存储 + JSON 导出。"""
import sqlite3, json, os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "market.db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS market_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, code TEXT, price REAL, change_pct REAL,
            volume REAL, high REAL, low REAL, open REAL, prev_close REAL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS stock_price (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT, name TEXT, price REAL, change_pct REAL, change_amt REAL,
            volume REAL, turnover REAL, high REAL, low REAL, open REAL, prev_close REAL,
            pe REAL, fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS portfolio_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_asset REAL, total_profit REAL, total_profit_pct REAL,
            cash REAL, cash_cow_pct REAL, growth_pct REAL, frontier_pct REAL,
            snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ai_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, source TEXT, url TEXT, category TEXT,
            published_at TEXT, fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS analysis_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_type TEXT,  -- 'morning_watch' / 'afternoon_watch' / 'weekly_scan' / 'dca_decision'
            market_state TEXT,   -- 大盘状态：bull/bear/shock
            index_data TEXT,     -- 指数快照 JSON
            holdings_review TEXT,-- 持仓复查 JSON
            signals TEXT,        -- 触发的信号
            decisions TEXT,      -- 决策思路和结论
            screener_output TEXT,-- 筛股输出
            raw_notes TEXT,      -- 原始备注
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_market_fetched ON market_index(fetched_at);
        CREATE INDEX IF NOT EXISTS idx_stock_fetched ON stock_price(fetched_at);
        CREATE INDEX IF NOT EXISTS idx_analysis_created ON analysis_log(created_at);
    """)
    conn.commit()
    conn.close()


def export_all_json():
    """将最新数据导出为 JSON，供前端 HTML 加载。"""
    conn = get_db()
    os.makedirs(DATA_DIR, exist_ok=True)

    # ── 大盘指数 ──
    cur = conn.execute("""
        SELECT DISTINCT name, code,
            FIRST_VALUE(price) OVER w AS price,
            FIRST_VALUE(change_pct) OVER w AS change_pct,
            FIRST_VALUE(volume) OVER w AS volume,
            FIRST_VALUE(high) OVER w AS high,
            FIRST_VALUE(low) OVER w AS low,
            FIRST_VALUE(open) OVER w AS open,
            FIRST_VALUE(prev_close) OVER w AS prev_close
        FROM market_index
        WHERE fetched_at > datetime('now', '-1 day')
        WINDOW w AS (PARTITION BY code ORDER BY fetched_at DESC)
    """)
    _write_json("market.json", cur.fetchall())

    # ── 个股行情 ──
    cur = conn.execute("""
        SELECT sp.* FROM stock_price sp
        INNER JOIN (
            SELECT code, MAX(fetched_at) AS mx FROM stock_price
            WHERE fetched_at > datetime('now', '-1 day')
            GROUP BY code
        ) latest ON sp.code = latest.code AND sp.fetched_at = latest.mx
        ORDER BY sp.code
    """)
    _write_json("stocks.json", cur.fetchall())

    # ── 持仓（从 sim-portfolio.json 读取） ──
    try:
        with open(os.path.expanduser("~/.hermes/portfolio/sim-portfolio.json")) as f:
            _write_json("portfolio.json", json.load(f))
    except Exception:
        _write_json("portfolio.json", {})

    # ── 资讯 ──
    cur = conn.execute("SELECT * FROM ai_news ORDER BY fetched_at DESC LIMIT 30")
    _write_json("news.json", cur.fetchall())

    # ── 大盘历史走势 ──
    cur = conn.execute("""
        SELECT fetched_at, name, price, change_pct FROM market_index
        ORDER BY fetched_at DESC LIMIT 90
    """)
    _write_json("history.json", cur.fetchall())

    # ── 资产快照历史 ──
    cur = conn.execute("SELECT * FROM portfolio_snapshot ORDER BY snapshot_at DESC LIMIT 60")
    _write_json("snapshots.json", cur.fetchall())

    # ── 分析日志 ──
    cur = conn.execute("SELECT * FROM analysis_log ORDER BY created_at DESC LIMIT 30")
    _write_json("analysis.json", cur.fetchall())

    conn.close()
    return True


def _write_json(filename, data):
    """将 Row 列表或 dict 写入 JSON 文件，带上时间戳。"""
    # 始终转为可序列化形式：Row → dict, list of Row → list of dict
    if isinstance(data, list):
        items = [dict(r) if hasattr(r, 'keys') else r for r in data]
    elif hasattr(data, 'keys'):
        items = dict(data)
    else:
        items = data
    payload = {"updated": datetime.now().isoformat(), "data": items}
    with open(os.path.join(DATA_DIR, filename), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, default=str)


if __name__ == "__main__":
    init_db()
    print("✅ 数据库初始化:", DB_PATH)