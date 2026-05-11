#!/usr/bin/env python3
"""
小智盯盘 V3.1 数据抓取引擎
- 从东方财富API拉取实时行情
- 从模拟盘引擎读取持仓
- 写入SQLite并导出JSON
- 支持定时调度和历史分析记录
"""

import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# === Configuration ===
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"
DB_PATH = BASE_DIR / "fetcher" / "dashboard.db"
SIM_ENGINE = BASE_DIR.parent / "v3.1-agent"

# Stock codes to track
WATCHLIST_CODES = [
    # Cash cows
    "600900",  # 长江电力
    "601088",  # 中国神华
    "600519",  # 贵州茅台
    "000858",  # 五粮液
    "000429",  # 粤高速A
    # Growth
    "600406",  # 国电南瑞
    "000400",  # 许继电气
    "002050",  # 三花智控
    "601689",  # 拓普集团
    "300308",  # 中际旭创
    "688256",  # 寒武纪
    "688041",  # 海光信息
    "600501",  # 航天晨光
]

INDEX_CODES = [
    ("1.000001", "上证指数"),
    ("0.399001", "深证成指"),
    ("0.399006", "创业板指"),
    ("1.000688", "科创50"),
    ("1.000300", "沪深300"),
]

SECTOR_CODES = [
    ("BK0737", "商业航天"), ("BK0429", "港口航运"), ("BK1163", "人形机器人"),
    ("BK1105", "CPO"), ("BK0451", "房地产"), ("BK1164", "光纤概念"),
    ("BK0914", "流感"), ("BK0581", "工业母机"), ("BK0732", "贵金属"),
    ("BK1036", "半导体"), ("BK0775", "能源金属"), ("BK0591", "电池"),
    ("BK0473", "证券"), ("BK0437", "煤炭"), ("BK0475", "银行"),
    ("BK0594", "风电设备"),
]

EASTMONEY_API = "https://push2.eastmoney.com/api/qt/ulist.np/get"

# ==================== Database ====================

def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db

def init_db():
    schema = BASE_DIR / "fetcher" / "schema.sql"
    if schema.exists():
        db = get_db()
        db.executescript(schema.read_text())
        db.commit()
        db.close()
        print("✅ 数据库初始化完成")

# ==================== API Fetchers ====================

def fetch_eastmoney(codes, market=1):
    """Fetch real-time quotes from East Money API.
    codes: list of (market_prefix.code, name) tuples
    market: 0=SZ, 1=SH, can also be 0.xxx for indices
    """
    secids = ",".join([c[0] for c in codes])
    params = {
        "fltt": "2",
        "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f12,f14,f15,f16,f17,f18,f20,f21",
        "secids": secids,
        "np": "1",
    }
    try:
        resp = requests.get(EASTMONEY_API, params=params, timeout=10)
        data = resp.json()
        if data.get("data") and data["data"].get("diff"):
            return data["data"]["diff"]
        return []
    except Exception as e:
        print(f"⚠️ 东方财富API请求失败: {e}")
        return []

def fetch_indices():
    """Fetch market index data."""
    code_map = {c[0]: c[1] for c in INDEX_CODES}
    diffs = fetch_eastmoney(INDEX_CODES)
    indices = []
    for d in diffs:
        code = d.get("f12", "")
        indices.append({
            "code": code,
            "name": code_map.get(code, d.get("f14", "")),
            "price": d.get("f2"),
            "change": d.get("f4"),
            "change_pct": d.get("f3"),
        })
    return indices

def fetch_sectors():
    """Fetch sector/板块 data."""
    # Use East Money sector list API
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    codes_str = ",".join([c[0] for c in SECTOR_CODES])
    params = {
        "pn": "1", "pz": "50",
        "po": "1", "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": f"b:{codes_str}",
        "fields": "f2,f3,f4,f12,f14",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("data") and data["data"].get("diff"):
            name_map = {c[0]: c[1] for c in SECTOR_CODES}
            sectors = []
            for d in data["data"]["diff"]:
                sectors.append({
                    "name": name_map.get(d.get("f12", ""), d.get("f14", "")),
                    "change_pct": d.get("f3"),
                })
            return sectors
    except Exception as e:
        print(f"⚠️ 板块数据请求失败: {e}")
    return []

def fetch_stocks(codes):
    """Fetch stock quotes for given codes."""
    # Determine market prefix
    items = []
    for code in codes:
        if code.startswith("6"):
            items.append((f"1.{code}", code))
        elif code.startswith("0") or code.startswith("3"):
            items.append((f"0.{code}", code))
        elif code.startswith("68"):
            items.append((f"1.{code}", code))
        else:
            items.append((f"1.{code}", code))
    
    diffs = fetch_eastmoney(items)
    stocks = []
    for d in diffs:
        code = d.get("f12", "")
        stocks.append({
            "code": code,
            "name": d.get("f14", ""),
            "price": d.get("f2"),
            "change_pct": d.get("f3"),
            "change": d.get("f4"),
            "volume": d.get("f5"),
            "turnover": d.get("f6"),
            "amplitude": d.get("f7"),
            "high": d.get("f15"),
            "low": d.get("f16"),
            "open": d.get("f17"),
            "prev_close": d.get("f18"),
            "pe": d.get("f9"),
            "pb": d.get("f20") or d.get("f21"),
        })
    return stocks

# ==================== Portfolio Reader ====================

def read_portfolio_state():
    """Read current portfolio state from sim engine."""
    state_file = SIM_ENGINE / "state.json"
    if not state_file.exists():
        print("⚠️ 模拟盘状态文件不存在")
        return None
    
    with open(state_file) as f:
        state = json.load(f)
    
    current = state.get("current", {})
    holdings_dict = current.get("holdings", {})
    trades = state.get("trades", [])
    
    # Build holdings list
    holdings = []
    total_mv = 0
    total_pnl = 0
    for code, h in holdings_dict.items():
        # Try to get live price
        price = h.get("avg_cost")  # fallback
        holdings.append({
            "code": code,
            "name": h.get("name", ""),
            "shares": h.get("shares", 0),
            "avg_cost": h.get("avg_cost", 0),
            "cost": h.get("shares", 0) * h.get("avg_cost", 0),
            "current_price": price,
            "market_value": h.get("shares", 0) * price,
            "pnl": h.get("shares", 0) * (price - h.get("avg_cost", 0)),
            "pnl_pct": (price / h.get("avg_cost", 0) - 1) * 100 if h.get("avg_cost") else 0,
            "type": h.get("type", ""),
            "sector": h.get("sector", ""),
        })
        total_mv += holdings[-1]["market_value"]
        total_pnl += holdings[-1]["pnl"]
    
    # Calculate summary
    total_assets = current.get("total_assets", 0)
    cash = current.get("cash", 0)
    peak = current.get("peak_assets", 100000)
    
    summary = {
        "total_assets": total_assets,
        "cash": cash,
        "cash_pct": round(cash / total_assets * 100, 1) if total_assets else 0,
        "market_value": total_mv,
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / (total_mv - total_pnl) * 100, 2) if (total_mv - total_pnl) else 0,
        "holding_count": len(holdings),
        "peak_assets": peak,
        "drawdown_pct": current.get("drawdown_pct", 0),
        "total_injected": current.get("total_injected", 0),
    }
    
    return {
        "summary": summary,
        "holdings": holdings,
        "trades": trades,
        "redlines": [
            {"name": "单票≤10%", "value": f"{max(h['market_value']/total_assets*100 for h in holdings):.1f}%" if holdings else "0%", "limit": "10%", "status": "ok"},
            {"name": "单行业≤20%", "value": "--", "limit": "20%", "status": "ok"},
            {"name": "现金≥10%", "value": f"{summary['cash_pct']:.1f}%", "limit": "10%", "status": "ok"},
            {"name": "回撤熔断", "value": f"{summary['drawdown_pct']:.2f}%", "limit": "15%", "status": "ok"},
        ]
    }

# ==================== Market State ====================

def determine_market_state(indices, sectors):
    """Determine market risk state from index and sector data."""
    # Get Shanghai composite
    sh = next((i for i in indices if i["code"] == "000001"), None)
    
    if not sh:
        return {
            "mode": "Neutral",
            "volume": "--",
            "up_down_ratio": "--",
            "reason": "数据不足",
        }
    
    # Count rising vs falling sectors
    rising = sum(1 for s in sectors if s.get("change_pct", 0) > 0)
    falling = len(sectors) - rising
    
    sh_change = sh.get("change_pct", 0) or 0
    
    # State decision
    if sh_change > 1.0 and rising > falling * 2:
        mode = "RiskOn"
        reason = "指数强势+板块普涨"
    elif sh_change < -2.0 or (falling > rising * 2):
        mode = "RiskOff"
        reason = "指数下跌+板块普跌"
    elif sh_change < -4.0:
        mode = "Panic"
        reason = "指数暴跌,触发恐慌"
    else:
        mode = "Neutral"
        reason = "指数震荡,板块分化"
    
    return {
        "mode": mode,
        "volume": "--",
        "up_down_ratio": f"{rising}涨 / {falling}跌",
        "north_flow": "待获取",
        "reason": reason,
    }

# ==================== News Fetcher (placeholder) ====================

def fetch_news():
    """Fetch market news. Currently returns static/cached data."""
    # In production, this would scrape from multiple sources
    # For now, return cached news from JSON
    news_file = DATA_DIR / "news.json"
    if news_file.exists():
        with open(news_file) as f:
            return json.load(f).get("items", [])
    return []

# ==================== JSON Export ====================

def export_json(filename, data):
    """Export data to JSON file."""
    path = DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {filename}")

def save_analysis_to_db(date_str, market_state, pelt_warnings, decisions, thoughts):
    """Save analysis record to SQLite."""
    db = get_db()
    db.execute("""
        INSERT OR REPLACE INTO analysis_log 
        (date, market_state, volume, up_down_ratio, state_reason, pelt_warnings, decisions, thoughts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        date_str,
        market_state.get("mode", ""),
        market_state.get("volume", ""),
        market_state.get("up_down_ratio", ""),
        market_state.get("reason", ""),
        json.dumps(pelt_warnings, ensure_ascii=False),
        json.dumps(decisions, ensure_ascii=False),
        thoughts,
    ))
    db.commit()
    db.close()

def export_analysis_json(date_str, market_state, pelt_warnings, decisions, thoughts):
    """Export analysis to JSON for frontend."""
    data = {
        "date": date_str,
        "analysis_time": datetime.now().strftime("%H:%M"),
        "market_state": market_state,
        "pelt_warnings": pelt_warnings,
        "decisions": decisions,
        "thoughts": thoughts,
    }
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    path = ANALYSIS_DIR / f"{date_str}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # Update index
    index_file = ANALYSIS_DIR / "index.json"
    dates = []
    if index_file.exists():
        dates = json.loads(index_file.read_text())
    if date_str not in dates:
        dates.append(date_str)
        dates.sort(reverse=True)
        with open(index_file, "w") as f:
            json.dump(dates, f, ensure_ascii=False)

# ==================== Main ====================

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "refresh"
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"\n{'='*60}")
    print(f"📊 小智盯盘数据引擎 | {now}")
    print(f"{'='*60}")
    
    init_db()
    
    if mode == "refresh":
        run_refresh(now)
    elif mode == "analysis":
        run_analysis(today, now)
    elif mode == "all":
        run_refresh(now)
        run_analysis(today, now)
    else:
        print(f"未知模式: {mode}")
        print("用法: fetch_data.py [refresh|analysis|all]")

def run_refresh(now):
    """Refresh market data JSON files."""
    print("\n📈 抓取市场数据...")
    
    # Fetch indices
    indices = fetch_indices()
    print(f"  指数: {len(indices)} 条")
    
    # Fetch sectors
    sectors = fetch_sectors()
    print(f"  板块: {len(sectors)} 条")
    
    # Determine market state
    state = determine_market_state(indices, sectors)
    print(f"  状态机: {state['mode']}")
    
    # Build market.json
    market_data = {
        "update_time": now,
        "indices": indices,
        "sectors": sectors,
        "state": state,
    }
    export_json("market.json", market_data)
    
    # Fetch watchlist stocks
    print("\n⭐ 抓取自选股...")
    live_stocks = fetch_stocks(WATCHLIST_CODES)
    print(f"  获取到 {len(live_stocks)} 只")
    
    # Merge with static watchlist data (for PE/PB/ROE which aren't in real-time API)
    watchlist_file = DATA_DIR / "watchlist.json"
    static = {}
    if watchlist_file.exists():
        with open(watchlist_file) as f:
            old = json.load(f)
            for s in old.get("stocks", []):
                static[s["code"]] = s
    
    stocks = []
    for live in live_stocks:
        code = live["code"]
        base = static.get(code, {})
        stocks.append({
            "code": code,
            "name": live.get("name") or base.get("name", ""),
            "price": live.get("price") or base.get("price"),
            "change_pct": live.get("change_pct") or 0,
            "pe": base.get("pe"),
            "pb": base.get("pb"),
            "roe": base.get("roe"),
            "dividend_yield": base.get("dividend_yield"),
            "type": base.get("type", "growth"),
            "status": base.get("status", "--"),
        })
    
    watchlist_data = {
        "update_time": now,
        "stocks": stocks,
    }
    export_json("watchlist.json", watchlist_data)
    
    # Read portfolio state
    print("\n💼 读取模拟盘持仓...")
    portfolio = read_portfolio_state()
    if portfolio:
        # Update with live prices
        live_map = {s["code"]: s.get("price") for s in live_stocks}
        for h in portfolio["holdings"]:
            if h["code"] in live_map and live_map[h["code"]]:
                price = live_map[h["code"]]
                h["current_price"] = price
                h["market_value"] = h["shares"] * price
                h["pnl"] = h["shares"] * (price - h["avg_cost"])
                h["pnl_pct"] = (price / h["avg_cost"] - 1) * 100 if h["avg_cost"] else 0
        
        # Recalculate summary
        holdings = portfolio["holdings"]
        total_mv = sum(h["market_value"] for h in holdings)
        total_cost = sum(h["cost"] for h in holdings)
        total_pnl = total_mv - total_cost
        s = portfolio["summary"]
        s["market_value"] = round(total_mv, 2)
        s["total_pnl"] = round(total_pnl, 2)
        s["total_pnl_pct"] = round(total_pnl / total_cost * 100, 2) if total_cost else 0
        
        portfolio["update_time"] = now
        export_json("positions.json", portfolio)
        print(f"  持仓: {len(holdings)} 只 | 总市值: {total_mv:.0f}")
    
    print(f"\n✅ 数据刷新完成")

def run_analysis(date_str, now):
    """Generate and save analysis record."""
    print(f"\n📝 生成分析记录: {date_str}")
    
    # Load current market data
    market_file = DATA_DIR / "market.json"
    market_state = {"mode": "Neutral", "volume": "--", "up_down_ratio": "--", "reason": "数据不足"}
    if market_file.exists():
        with open(market_file) as f:
            market = json.load(f)
            market_state = market.get("state", market_state)
    
    # Generate PELT warnings from watchlist
    watchlist_file = DATA_DIR / "watchlist.json"
    pelt_warnings = []
    if watchlist_file.exists():
        with open(watchlist_file) as f:
            wl = json.load(f)
            for s in wl.get("stocks", []):
                pe = s.get("pe")
                if pe is not None and pe < 0:
                    pelt_warnings.append({"code": s["code"], "stock": s["name"], "warning": f"PE为负({pe})，持续亏损"})
                elif pe is not None and pe > 100:
                    pelt_warnings.append({"code": s["code"], "stock": s["name"], "warning": f"PE {pe}x极高，估值风险大"})
    
    # Load portfolio for decisions
    decisions = []
    positions_file = DATA_DIR / "positions.json"
    if positions_file.exists():
        with open(positions_file) as f:
            pos = json.load(f)
            for h in pos.get("holdings", []):
                if h.get("pnl_pct", 0) < -5:
                    decisions.append({"action": "⚠️ 止损预警", "detail": f"{h['name']}({h['code']}) 浮亏 {h['pnl_pct']:.1f}%，触发基础止损线"})
        
        if not decisions:
            decisions.append({"action": "持仓不动", "detail": "所有标的在安全区间内，无需操作"})
    
    # Thoughts template
    thoughts = f"""【市场状态】当前状态机判定为 {market_state.get('mode', 'N/A')}，{market_state.get('reason', '')}。

【持仓评估】所有持仓标的需要逐项检查：止损线、行业集中度、单票比例。

【定投策略】月度定投日12号，关注现金牛60%/成长股30%配置比例。

【风险关注】关注上证4200压力位、北向资金流向、行业轮动节奏。"""
    
    # Save to DB
    save_analysis_to_db(date_str, market_state, pelt_warnings, decisions, thoughts)
    
    # Export JSON
    export_analysis_json(date_str, market_state, pelt_warnings, decisions, thoughts)
    
    print(f"  ✅ 分析记录已保存")

if __name__ == "__main__":
    main()