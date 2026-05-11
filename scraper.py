# -*- coding: utf-8 -*-
"""V3.1 Dashboard — Data collector. Fetches from 东方财富 API and stores in SQLite."""
import os
import sys
import json
import time
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from db import get_db, init_db, export_all_json

# ── EastMoney API endpoints ──
MARKET_URL = "https://push2.eastmoney.com/api/qt/ulist.np?fltt=2&fields=f2,f3,f4,f5,f6,f7,f15,f16,f17,f18&secids=1.000001,0.399001,0.399006"
STOCK_URL_TEMPLATE = "https://push2.eastmoney.com/api/qt/stock/get?secid={market}.{code}&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f60,f116,f117,f162,f167,f168,f169,f170,f171"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={market}.{code}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&end=20500101&lmt=5"

# Stock watchlist: (code, market: 0=SZ, 1=SH)
WATCHLIST = [
    ("000858", 0, "五粮液"),
    ("601088", 1, "中国神华"),
    ("000429", 0, "粤高速A"),
    ("600941", 1, "中国移动"),
    ("601398", 1, "工商银行"),
    ("601689", 0, "拓普集团"),
    ("002050", 0, "三花智控"),
    ("600519", 1, "贵州茅台"),
    ("600900", 1, "长江电力"),
    ("600436", 1, "片仔癀"),
    ("688256", 1, "寒武纪"),
    ("300308", 0, "中际旭创"),
    ("688041", 1, "海光信息"),
    ("600406", 1, "国电南瑞"),
    ("000400", 0, "许继电气"),
    ("600391", 1, "航天晨光"),
    ("003031", 0, "江顺科技"),
]

MARKET_NAMES = {
    "1.000001": "上证指数", "0.399001": "深证成指", "0.399006": "创业板指"
}


def fetch_json(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    req.add_header("Referer", "https://quote.eastmoney.com/")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect_market(conn):
    """Fetch and store market indices."""
    print("📊 拉取大盘指数...")
    data = fetch_json(MARKET_URL)
    rows = data.get("data", {}).get("diff", [])
    for row in rows:
        secid = row.get("f12", "")
        name = MARKET_NAMES.get(secid, secid)
        conn.execute("""
            INSERT INTO market_index (name, code, price, change_pct, volume, high, low, open, prev_close)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, secid,
            row.get("f2") / 100 if row.get("f2") else None,
            row.get("f3") / 100 if row.get("f3") else None,
            row.get("f6") or row.get("f5"),
            row.get("f15") / 100 if row.get("f15") else None,
            row.get("f16") / 100 if row.get("f16") else None,
            row.get("f17") / 100 if row.get("f17") else None,
            row.get("f18") / 100 if row.get("f18") else None,
        ))
    conn.commit()
    print(f"   已写入 {len(rows)} 条指数数据")


def collect_stocks(conn):
    """Fetch and store stock prices for watchlist."""
    print("📈 拉取个股行情...")
    count = 0
    for code, market, name in WATCHLIST:
        try:
            mkt = {0: "0", 1: "1"}[market]
            url = STOCK_URL_TEMPLATE.format(market=mkt, code=code)
            data = fetch_json(url)
            d = data.get("data", {})
            if not d:
                continue

            conn.execute("""
                INSERT INTO stock_price (code, name, price, change_pct, change_amt, volume,
                    turnover, high, low, open, prev_close, pe)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"{mkt}.{code}", name,
                d.get("f43") / 100 if d.get("f43") else None,
                d.get("f170") / 100 if d.get("f170") else None,
                d.get("f169") / 100 if d.get("f169") else None,
                d.get("f47"),
                d.get("f48"),
                d.get("f44") / 100 if d.get("f44") else None,
                d.get("f45") / 100 if d.get("f45") else None,
                d.get("f46") / 100 if d.get("f46") else None,
                d.get("f60") / 100 if d.get("f60") else None,
                d.get("f162") / 100 if d.get("f162") else None,
            ))
            count += 1
            time.sleep(0.15)  # Rate limit
        except Exception as e:
            print(f"   ⚠️ {name}({code}) 失败: {e}")
    conn.commit()
    print(f"   已写入 {count} 只股票数据")


def collect_portfolio_snapshot(conn):
    """Save portfolio snapshot."""
    try:
        with open(os.path.expanduser("~/.hermes/portfolio/sim-portfolio.json")) as f:
            port = json.load(f)
    except Exception:
        return

    holdings = port.get("holdings", [])
    cash = float(port.get("cash", 49000))
    total_cost = sum(h.get("total_cost", 0) for h in holdings)
    total_market = sum((h.get("current_price", 0) or 0) * (h.get("shares", 0) or 0) for h in holdings)
    total_asset = cash + total_market
    total_profit = total_asset - 100000

    # Classify
    cash_cow_mv = sum((h.get("current_price", 0) or 0) * h.get("shares", 0) for h in holdings if h.get("category") == "现金牛")
    growth_mv = sum((h.get("current_price", 0) or 0) * h.get("shares", 0) for h in holdings if h.get("category") == "成长股")
    frontier_mv = sum((h.get("current_price", 0) or 0) * h.get("shares", 0) for h in holdings if h.get("category") == "拓荒型")

    conn.execute("""
        INSERT INTO portfolio_snapshot (total_asset, total_profit, total_profit_pct, cash,
            cash_cow_pct, growth_pct, frontier_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        round(total_asset, 2),
        round(total_profit, 2),
        round(total_profit / 100000 * 100, 2) if total_asset > 0 else 0,
        round(cash, 2),
        round(cash_cow_mv / total_asset * 100, 1) if total_asset > 0 else 0,
        round(growth_mv / total_asset * 100, 1) if total_asset > 0 else 0,
        round(frontier_mv / total_asset * 100, 1) if total_asset > 0 else 0,
    ))
    conn.commit()
    print("💰 持仓快照已保存")


def main():
    init_db()
    conn = get_db()
    try:
        collect_market(conn)
        collect_stocks(conn)
        collect_portfolio_snapshot(conn)
        export_all_json()
        print("✅ 数据采集完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()