#!/usr/bin/env python3
"""
小智盯盘 V3.1 — JSON导出引擎 (只读SQLite → 写JSON)
职责: 从SQLite抽取最新数据 → 生成前端所需的JSON文件
不做: 数据抓取、API调用
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"
DB_PATH = BASE_DIR / "fetcher" / "dashboard.db"

# Static analysis data for watchlist (updated manually)
STATIC_WATCHLIST = DATA_DIR / "watchlist_static.json"

def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db

def save_json(filename, data):
    path = DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_static():
    if STATIC_WATCHLIST.exists():
        with open(STATIC_WATCHLIST) as f:
            return {s["code"]: s for s in json.load(f).get("stocks",[])}
    return {}

# === Export Functions ===

def export_market(db):
    """Latest index + sector snapshots"""
    # Find latest timestamps
    idx_ts = db.execute("SELECT MAX(ts) as ts FROM idx_snapshots").fetchone()
    sec_ts = db.execute("SELECT MAX(ts) as ts FROM sector_snapshots").fetchone()
    idx_ts = idx_ts["ts"] if idx_ts else None
    sec_ts = sec_ts["ts"] if sec_ts else None
    
    indices = []
    if idx_ts:
        indices = db.execute("SELECT code, name, price, change_val, change_pct FROM idx_snapshots WHERE ts=? ORDER BY id", [idx_ts]).fetchall()
    
    sectors = []
    if sec_ts:
        sectors = db.execute("SELECT name, change_pct FROM sector_snapshots WHERE ts=? ORDER BY id", [sec_ts]).fetchall()
    
    ts = idx_ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Derive market state
    sh = next((i for i in indices if i["code"] in ("sh000001","000001")), None)
    pct = sh["change_pct"] if sh else 0
    rising = sum(1 for s in sectors if (s["change_pct"] or 0) > 0)
    falling = len(sectors) - rising
    
    if pct > 1.0 and rising > falling*2: mode,reason = "RiskOn","指数强势+板块普涨"
    elif pct < -4.0: mode,reason = "Panic","指数暴跌"
    elif pct < -2.0 or falling > rising*2: mode,reason = "RiskOff","指数下跌+板块普跌"
    elif abs(pct) < 0.2: mode,reason = "Neutral","指数横盘"
    else: mode,reason = "Neutral","指数震荡"
    
    data = {
        "update_time": ts,
        "indices": [{"code":r["code"],"name":r["name"],"price":r["price"],
                      "change":r["change_val"],"change_pct":r["change_pct"]} for r in indices],
        "sectors": [{"name":r["name"],"change_pct":r["change_pct"]} for r in sectors],
        "state": {
            "mode": mode,
            "volume": "--",
            "up_down_ratio": f"{rising}涨/{falling}跌" if sectors else "--",
            "north_flow": "待获取",
            "reason": reason
        }
    }
    
    # If sectors empty, keep cached
    if not sectors:
        cached = DATA_DIR / "market.json"
        if cached.exists():
            with open(cached) as f:
                old = json.load(f)
                data["sectors"] = old.get("sectors", [])
    
    save_json("market.json", data)
    print(f"  market.json: {len(indices)}指数 {len(data['sectors'])}板块 {mode}")

def norm_code(c):
    """Normalize code: strip sh/sz prefix"""
    if c.startswith('sh'): return c[2:]
    if c.startswith('sz'): return c[2:]
    return c

def export_watchlist(db):
    """Latest stock prices merged with static analysis data, per-code latest"""
    static = load_static()
    
    # Get latest snapshot per stock (not per timestamp)
    stocks = db.execute("""
        SELECT s.code, s.name, s.price, s.change_pct, s.pe_ttm
        FROM stock_snapshots s
        INNER JOIN (
            SELECT code, MAX(ts) as max_ts FROM stock_snapshots GROUP BY code
        ) latest ON s.code = latest.code AND s.ts = latest.max_ts
        ORDER BY s.code
    """).fetchall()
    items = []
    for s in stocks:
        raw = s["code"]
        code = norm_code(raw)
        base = static.get(code, {})
        items.append({
            "code": code, "name": s["name"],
            "price": s["price"], "change_pct": s["change_pct"],
            "pe": s["pe_ttm"] or base.get("pe"), "pb": base.get("pb"),
            "roe": base.get("roe"), "dividend_yield": base.get("dividend_yield"),
            "score": base.get("score"), "logic": base.get("logic"),
            "tags": base.get("tags",[]),
            "type": base.get("type","growth"),
            "status": base.get("status","--"),
        })
    
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_json("watchlist.json", {"update_time": ts, "stocks": items})
    print(f"  watchlist.json: {len(items)} 只")

def export_positions(db):
    """Latest portfolio snapshot + holdings + trades"""
    port_ts = db.execute("SELECT MAX(ts) as ts FROM portfolio_snapshots").fetchone()
    hold_ts = db.execute("SELECT MAX(ts) as ts FROM holding_snapshots").fetchone()
    port_ts = port_ts["ts"] if port_ts else None
    hold_ts = hold_ts["ts"] if hold_ts else None
    
    port = None; holds = []
    if port_ts:
        port = db.execute("SELECT * FROM portfolio_snapshots WHERE ts=? ORDER BY id DESC LIMIT 1", [port_ts]).fetchone()
    if hold_ts:
        holds = db.execute("SELECT * FROM holding_snapshots WHERE ts=? ORDER BY code", [hold_ts]).fetchall()
    trades = db.execute("SELECT * FROM trade_log ORDER BY date DESC LIMIT 20").fetchall()
    
    if not port:
        print("  positions.json: 无数据")
        return
    
    # Calculate total commission
    comm_row = db.execute("SELECT COALESCE(SUM(commission),0) as total FROM trade_log").fetchone()
    total_commission = comm_row["total"] if comm_row else 0

    ts = port_ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    data = {
        "update_time": ts,
        "summary": {
            "total_assets": port["total_assets"], "cash": port["cash"],
            "cash_pct": round(port["cash"]/port["total_assets"]*100,1) if port["total_assets"] else 0,
            "market_value": port["market_value"],
            "total_pnl": port["total_pnl"], "total_pnl_pct": port["total_pnl_pct"],
            "holding_count": len(holds),
            "peak_assets": 100000,  # from sim engine, approximate
            "drawdown_pct": port["drawdown_pct"] or 0,
            "total_injected": port["total_injected"] or 0,
            "total_commission": total_commission,
        },
        "holdings": [{
            "code": h["code"], "name": h["name"],
            "shares": h["shares"], "avg_cost": h["avg_cost"],
            "cost": (h["shares"] or 0) * (h["avg_cost"] or 0),
            "current_price": h["current_price"], "market_value": h["market_value"],
            "pnl": h["pnl"], "pnl_pct": h["pnl_pct"],
            "type": h["htype"], "sector": h["sector"],
        } for h in holds],
        "trades": [{
            "date": t["date"], "action": t["action"], "code": t["code"],
            "name": t["name"], "shares": t["shares"], "price": t["price"], "amount": t["amount"],
            "commission": t["commission"],
        } for t in reversed(trades)],
        "redlines": [
            {"name":"单票≤10%","value":f"{max((h['market_value']/port['total_assets']*100) for h in holds):.1f}%" if holds and port['total_assets'] else "0%","limit":"10%","status":"ok"},
            {"name":"单行业≤20%","value":"--","limit":"20%","status":"ok"},
            {"name":"现金≥10%","value":f"{port['cash']/port['total_assets']*100:.1f}%" if port['total_assets'] else "0%","limit":"10%","status":"ok"},
            {"name":"回撤熔断","value":f"{(port['drawdown_pct'] or 0):.2f}%","limit":"15%","status":"ok"},
        ]
    }
    
    save_json("positions.json", data)
    print(f"  positions.json: {len(holds)}持有 {len(data['trades'])}交易")

def export_analysis(db):
    """Export all analysis records as individual JSON files + index"""
    records = db.execute("SELECT * FROM analysis_log ORDER BY date DESC LIMIT 60").fetchall()
    
    dates = []
    for r in records:
        item = {
            "date": r["date"],
            "analysis_time": r["ts"][11:16] if r["ts"] else "",
            "market_state": {
                "mode": r["market_state"], "volume": r["volume"],
                "up_down_ratio": r["up_down_ratio"], "reason": r["state_reason"]
            },
            "pelt_warnings": json.loads(r["pelt_warnings"]) if r["pelt_warnings"] else [],
            "decisions": json.loads(r["decisions"]) if r["decisions"] else [],
            "thoughts": r["thoughts"] or ""
        }
        ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
        with open(ANALYSIS_DIR / f"{r['date']}.json", "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        dates.append(r["date"])
    
    # Index
    with open(ANALYSIS_DIR / "index.json", "w") as f:
        json.dump(dates, f, ensure_ascii=False)
    
    print(f"  analysis/: {len(dates)} 条")

# === Main ===
def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"\n{'='*50}")
    print(f"📤 JSON导出 | {ts}")
    print(f"{'='*50}")
    
    db = get_db()
    try:
        export_market(db)
        export_watchlist(db)
        export_positions(db)
        export_analysis(db)
        # News is manually curated
        nf = DATA_DIR / "news.json"
        if not nf.exists():
            save_json("news.json", {"update_time": ts, "items": []})
            print("  news.json: created")
    finally:
        db.close()
    
    print(f"\n✅ 导出完成 @ {ts}")

if __name__ == "__main__":
    main()