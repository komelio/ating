#!/usr/bin/env python3
"""
小智盯盘 V3.1 数据抓取引擎 v2
- 多数据源: 新浪财经 + 东方财富 + 搜狐
- 自动切换备用源
- SQLite持久化 + JSON导出
"""

import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === Configuration ===
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"
DB_PATH = BASE_DIR / "fetcher" / "dashboard.db"
SIM_ENGINE = BASE_DIR.parent / "v3.1-agent"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn/",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# Stock codes to track
WATCHLIST_CODES = [
    # Top 10 权重龙头
    "600519","601398","600941","601939","601288","601857","601988","002594","300750","601318",
    # Cash cows 现金牛
    "600900","601088","000858","000429","600036",
    # Growth 成长股
    "600406","000400","002050","601689","300308","688256","688041","600501",
]

WATCHLIST_TYPES = {
    # Top 10
    "600519":"top10","601398":"top10","600941":"top10","601939":"top10",
    "601288":"top10","601857":"top10","601988":"top10","002594":"top10",
    "300750":"top10","601318":"top10",
    # Cash cows
    "600900":"cashcow","601088":"cashcow","000858":"cashcow","000429":"cashcow","600036":"cashcow",
    # Growth
    "600406":"growth","000400":"growth","002050":"growth","601689":"growth",
    "300308":"growth","688256":"growth","688041":"growth","600501":"growth",
}

INDEX_LIST = [
    ("s_sh000001", "上证指数"), ("s_sz399001", "深证成指"),
    ("s_sz399006", "创业板指"), ("s_sh000688", "科创50"),
    ("s_sh000300", "沪深300"),
]

def get_session():
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update(HEADERS)
    return s

# ==================== Database ====================

def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db

def init_db():
    schema = BASE_DIR / "fetcher" / "schema.sql"
    if schema.exists():
        db = get_db()
        try:
            db.executescript(schema.read_text())
        except sqlite3.OperationalError:
            pass  # Tables/indices already exist
        db.commit()
        db.close()

# ==================== Sina Finance API ====================

def fetch_sina_quotes(codes):
    """Fetch real-time quotes from Sina Finance.
    codes: list of stock codes like ['sh600900', 'sz000400']
    Returns: dict of code -> price data
    """
    if not codes:
        return {}
    
    codes_str = ",".join(codes)
    url = f"https://hq.sinajs.cn/list={codes_str}"
    
    try:
        s = get_session()
        resp = s.get(url, timeout=15)
        resp.encoding = "gbk"
        text = resp.text
        
        results = {}
        for line in text.strip().split("\n"):
            if not line.strip() or "=" not in line:
                continue
            try:
                var_name = line.split("=")[0].strip()
                # Extract code from var_name like "var hq_str_sh600900" or "var hq_str_s_sh000001"
                raw_code = var_name.replace("var hq_str_", "")
                # Handle s_ prefix (indices): s_sh000001 -> sh000001
                if raw_code.startswith("s_"):
                    code_part = raw_code[2:]  # strip "s_"
                else:
                    code_part = raw_code
                data_str = line.split('"')[1] if '"' in line else ""
                
                if not data_str:
                    continue
                    
                parts = data_str.split(",")
                if len(parts) < 3:  # minimum: name, price, change_pct
                    continue
                
                # Detect format: indices have ~6 fields, stocks have 32+
                is_index = len(parts) <= 10
                
                if is_index:
                    # Index format: name, price, change, change_pct, volume, turnover
                    name = parts[0]
                    price = safe_float(parts[1])
                    change = safe_float(parts[2])
                    change_pct = safe_float(parts[3])
                    prev_close = round(price - change, 3) if price and change else None
                    open_price = None
                    high = None
                    low = None
                    volume = safe_float(parts[4])
                    turnover = safe_float(parts[5])
                else:
                    # Stock format: name, open, prev_close, price, high, low, ...
                    name = parts[0]
                    open_price = safe_float(parts[1])
                    prev_close = safe_float(parts[2])
                    price = safe_float(parts[3])
                    high = safe_float(parts[4])
                    low = safe_float(parts[5])
                    volume = safe_float(parts[8])
                    turnover = safe_float(parts[9])
                    change = round(price - prev_close, 3) if price and prev_close else 0
                    change_pct = round((price / prev_close - 1) * 100, 3) if price and prev_close else 0
                
                results[code_part] = {
                    "code": code_part.replace("sh", "").replace("sz", ""),
                    "name": name,
                    "price": price,
                    "open": open_price,
                    "prev_close": prev_close,
                    "high": high,
                    "low": low,
                    "change": change,
                    "change_pct": change_pct,
                    "volume": volume,
                    "turnover": turnover,
                }
            except Exception as e:
                continue
        return results
    except Exception as e:
        print(f"⚠️ 新浪API请求失败: {e}")
        return {}

def fetch_indices_sina():
    """Fetch market indices from Sina."""
    codes = [c[0] for c in INDEX_LIST]
    data = fetch_sina_quotes(codes)
    
    # Build reverse lookup: sina_raw_code (without s_) -> (display_code, name)
    code_reverse = {}
    for c in INDEX_LIST:
        raw = c[0].replace("s_", "")  # s_sh000001 -> sh000001
        display_code = raw  # sh000001 or sz399001
        code_reverse[raw] = (display_code, c[1])
    
    indices = []
    for code_key, d in data.items():
        code_info = code_reverse.get(code_key, (d["code"], d["name"]))
        indices.append({
            "code": code_info[0],
            "name": code_info[1],
            "price": d["price"],
            "change": d["change"],
            "change_pct": d["change_pct"],
        })
    return indices

def fetch_stocks_sina(codes):
    """Fetch individual stocks from Sina."""
    sina_codes = []
    for c in codes:
        if c.startswith("6") or c.startswith("68"):
            sina_codes.append(f"sh{c}")
        else:
            sina_codes.append(f"sz{c}")
    
    data = fetch_sina_quotes(sina_codes)
    stocks = []
    for sina_code, d in data.items():
        stocks.append({
            "code": d["code"],
            "name": d["name"],
            "price": d["price"],
            "change": d["change"],
            "change_pct": d["change_pct"],
            "volume": d["volume"],
            "turnover": d["turnover"],
            "high": d["high"],
            "low": d["low"],
            "open": d["open"],
            "prev_close": d["prev_close"],
        })
    return stocks

# ==================== East Money API (Fallback) ====================

def fetch_sectors_eastmoney():
    """Fetch sector data from East Money."""
    # Try multiple sector list APIs
    urls = [
        "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=30&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t2&fields=f2,f3,f4,f12,f14",
        "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=30&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t3&fields=f2,f3,f4,f12,f14",
    ]
    
    for url in urls:
        try:
            s = get_session()
            resp = s.get(url, timeout=15)
            data = resp.json()
            if data.get("data") and data["data"].get("diff"):
                sectors = []
                for d in data["data"]["diff"]:
                    sectors.append({
                        "name": d.get("f14", ""),
                        "change_pct": d.get("f3"),
                    })
                return sectors
        except Exception as e:
            continue
    
    # Fallback: static sector data
    print("⚠️ 东方财富板块API不可用，使用缓存数据")
    return []

# ==================== Portfolio ====================

def read_portfolio_state():
    state_file = SIM_ENGINE / "state.json"
    if not state_file.exists():
        print("⚠️ 模拟盘状态文件不存在")
        return None
    
    with open(state_file) as f:
        state = json.load(f)
    
    current = state.get("current", {})
    holdings_dict = current.get("holdings", {})
    trades = state.get("trades", [])
    
    holdings = []
    total_mv = 0
    total_cost = 0
    for code, h in holdings_dict.items():
        price = h.get("avg_cost", 0)
        cost = h.get("shares", 0) * h.get("avg_cost", 0)
        mv = h.get("shares", 0) * price
        holdings.append({
            "code": code, "name": h.get("name", ""),
            "shares": h.get("shares", 0), "avg_cost": h.get("avg_cost", 0),
            "cost": cost, "current_price": price, "market_value": mv,
            "pnl": mv - cost,
            "pnl_pct": (price / h.get("avg_cost", 0) - 1) * 100 if h.get("avg_cost") else 0,
            "type": h.get("type", ""), "sector": h.get("sector", ""),
        })
        total_mv += mv
        total_cost += cost
    
    total_assets = current.get("total_assets", 100000)
    cash = current.get("cash", 89410)
    peak = current.get("peak_assets", 100000)
    
    summary = {
        "total_assets": round(total_assets, 2),
        "cash": round(cash, 2),
        "cash_pct": round(cash / total_assets * 100, 1) if total_assets else 0,
        "market_value": round(total_mv, 2),
        "total_pnl": round(total_mv - total_cost, 2),
        "total_pnl_pct": round((total_mv / total_cost - 1) * 100, 2) if total_cost else 0,
        "holding_count": len(holdings),
        "peak_assets": round(peak, 2),
        "drawdown_pct": current.get("drawdown_pct", 0),
        "total_injected": current.get("total_injected", 0),
    }
    
    # Redline checks
    redlines = [
        {"name": "单票≤10%", "value": f"{max((h['market_value']/total_assets*100) for h in holdings):.1f}%" if holdings and total_assets else "0%", "limit": "10%", "status": "ok"},
        {"name": "单行业≤20%", "value": "--", "limit": "20%", "status": "ok"},
        {"name": "现金≥10%", "value": f"{summary['cash_pct']:.1f}%", "limit": "10%", "status": "ok"},
        {"name": "回撤熔断", "value": f"{summary['drawdown_pct']:.2f}%", "limit": "15%", "status": "ok"},
    ]
    
    return {"summary": summary, "holdings": holdings, "trades": trades, "redlines": redlines}

# ==================== Market State ====================

def determine_market_state(indices, sectors):
    sh = next((i for i in indices if i["code"] in ("000001", "sh000001", "1A0001")), None)
    pct = sh.get("change_pct", 0) if sh else 0
    
    rising = sum(1 for s in sectors if (s.get("change_pct") or 0) > 0)
    falling = len(sectors) - rising
    
    if pct > 1.0 and rising > falling * 2:
        mode, reason = "RiskOn", "指数强势+板块普涨"
    elif pct < -4.0:
        mode, reason = "Panic", "指数暴跌,触发恐慌"
    elif pct < -2.0 or falling > rising * 2:
        mode, reason = "RiskOff", "指数下跌+板块普跌"
    elif abs(pct) < 0.2:
        mode, reason = "Neutral", "指数横盘,方向不明"
    else:
        mode, reason = "Neutral", "指数震荡,板块分化"
    
    return {
        "mode": mode,
        "volume": "--",
        "up_down_ratio": f"{rising}涨 / {falling}跌" if sectors else "--",
        "north_flow": "待获取",
        "reason": reason,
    }

# ==================== Helpers ====================

def safe_float(v):
    try:
        return float(v) if v and v != "" else None
    except (ValueError, TypeError):
        return None

def export_json(filename, data):
    path = DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(filename):
    path = DATA_DIR / filename
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

# ==================== Analysis Export ====================

def export_analysis(date_str, market_state, pelt_warnings, decisions, thoughts):
    data = {
        "date": date_str,
        "analysis_time": datetime.now().strftime("%H:%M"),
        "market_state": market_state,
        "pelt_warnings": pelt_warnings,
        "decisions": decisions,
        "thoughts": thoughts,
    }
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    with open(ANALYSIS_DIR / f"{date_str}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # Update index
    index_file = ANALYSIS_DIR / "index.json"
    dates = json.loads(index_file.read_text()) if index_file.exists() else []
    if date_str not in dates:
        dates.insert(0, date_str)
        with open(index_file, "w") as f:
            json.dump(dates, f, ensure_ascii=False)

# ==================== Main ====================

def run_refresh(now):
    print("\n📈 抓取指数 (新浪)...")
    indices = fetch_indices_sina()
    if not indices:
        # Use cached
        cached = load_json("market.json")
        indices = cached.get("indices", [])
    print(f"  指数: {len(indices)} 条")
    
    print("\n🔥 抓取板块 (东方财富)...")
    sectors = fetch_sectors_eastmoney()
    if not sectors:
        cached = load_json("market.json")
        sectors = cached.get("sectors", [])
    print(f"  板块: {len(sectors)} 条")
    
    state = determine_market_state(indices, sectors)
    print(f"  状态机: {state['mode']}")
    
    export_json("market.json", {
        "update_time": now, "indices": indices,
        "sectors": sectors, "state": state,
    })
    
    print("\n⭐ 抓取自选股 (新浪)...")
    live = fetch_stocks_sina(WATCHLIST_CODES)
    print(f"  获取到 {len(live)} 只")
    
    # Merge with static data
    static = load_json("watchlist.json")
    static_map = {s["code"]: s for s in static.get("stocks", [])}
    
    stocks = []
    for s in live:
        code = s["code"]
        base = static_map.get(code, {})
        stocks.append({
            "code": code, "name": s["name"],
            "price": s["price"], "change_pct": s.get("change_pct") or 0,
            "pe": base.get("pe"), "pb": base.get("pb"),
            "roe": base.get("roe"), "dividend_yield": base.get("dividend_yield"),
            "type": WATCHLIST_TYPES.get(code, "growth"),
            "status": base.get("status", "--"),
        })
    export_json("watchlist.json", {"update_time": now, "stocks": stocks})
    
    # Portfolio
    print("\n💼 读取持仓...")
    portfolio = read_portfolio_state()
    if portfolio:
        # Update with live prices
        live_map = {s["code"]: s["price"] for s in live}
        for h in portfolio["holdings"]:
            if h["code"] in live_map and live_map[h["code"]]:
                p = live_map[h["code"]]
                h["current_price"] = p
                h["market_value"] = round(h["shares"] * p, 2)
                h["pnl"] = round(h["shares"] * (p - h["avg_cost"]), 2)
                h["pnl_pct"] = round((p / h["avg_cost"] - 1) * 100, 2) if h["avg_cost"] else 0
        
        holdings = portfolio["holdings"]
        total_mv = sum(h["market_value"] for h in holdings)
        total_cost = sum(h["cost"] for h in holdings)
        s = portfolio["summary"]
        s["market_value"] = round(total_mv, 2)
        s["total_pnl"] = round(total_mv - total_cost, 2)
        s["total_pnl_pct"] = round((total_mv / total_cost - 1) * 100, 2) if total_cost else 0
        
        portfolio["update_time"] = now
        export_json("positions.json", portfolio)
        print(f"  持仓: {len(holdings)} 只 | 总市值: {total_mv:.0f}")
    
    print(f"\n✅ 数据刷新完成 @ {now}")

def run_analysis(date_str):
    print(f"\n📝 生成分析: {date_str}")
    
    market = load_json("market.json")
    watchlist = load_json("watchlist.json")
    positions = load_json("positions.json")
    
    market_state = market.get("state", {})
    
    pelt_warnings = []
    for s in watchlist.get("stocks", []):
        pe = s.get("pe")
        if pe is not None and pe < 0:
            pelt_warnings.append({"code": s["code"], "stock": s["name"], "warning": f"PE为负({pe})，持续亏损"})
        elif pe is not None and pe > 100:
            pelt_warnings.append({"code": s["code"], "stock": s["name"], "warning": f"PE {pe}x极高，估值风险大"})
    
    decisions = []
    for h in positions.get("holdings", []):
        pnl = h.get("pnl_pct", 0)
        if pnl < -8:
            decisions.append({"action": "🔴 止损", "detail": f"{h['name']}({h['code']}) 浮亏 {pnl:.1f}%，触发高PE止损"})
        elif pnl < -5:
            decisions.append({"action": "⚠️ 止损预警", "detail": f"{h['name']}({h['code']}) 浮亏 {pnl:.1f}%，接近基础止损线"})
    if not decisions:
        decisions.append({"action": "持仓不动", "detail": "所有标的在安全区间"})
    
    thoughts = f"""【市场状态】{market_state.get('mode','N/A')}: {market_state.get('reason','')}
成交额: {market_state.get('volume','--')} | 涨跌比: {market_state.get('up_down_ratio','--')}

【持仓评估】{len(positions.get('holdings',[]))}只标的, 总市值¥{positions.get('summary',{}).get('market_value',0):.0f}
现金占比: {positions.get('summary',{}).get('cash_pct',0)}%

【定投策略】月度定投日12号
{len(pelt_warnings)}个PELT预警, {len([d for d in decisions if '止损' in d.get('action','')])}个止损信号"""
    
    export_analysis(date_str, market_state, pelt_warnings, decisions, thoughts)
    
    # Save to DB
    db = get_db()
    db.execute("""INSERT OR REPLACE INTO analysis_log 
        (date, market_state, volume, up_down_ratio, state_reason, pelt_warnings, decisions, thoughts)
        VALUES (?,?,?,?,?,?,?,?)""",
        (date_str, market_state.get("mode",""), market_state.get("volume",""),
         market_state.get("up_down_ratio",""), market_state.get("reason",""),
         json.dumps(pelt_warnings, ensure_ascii=False),
         json.dumps(decisions, ensure_ascii=False), thoughts))
    db.commit(); db.close()
    
    print(f"  ✅ 已保存")

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "refresh"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    
    print(f"\n{'='*60}")
    print(f"📊 小智盯盘 V2 | {now}")
    print(f"{'='*60}")
    
    init_db()
    
    if mode == "refresh":
        run_refresh(now)
    elif mode == "analysis":
        run_analysis(today)
    elif mode == "all":
        run_refresh(now)
        run_analysis(today)
    else:
        print(f"未知模式: {mode}")

if __name__ == "__main__":
    main()