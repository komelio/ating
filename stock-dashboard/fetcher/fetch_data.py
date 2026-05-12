#!/usr/bin/env python3
"""
小智盯盘 V3.1 — 数据抓取引擎 (仅写SQLite)
职责: 从API拉数据 → 写入SQLite各表(增量追加)
不做: JSON导出、页面渲染
"""

import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "fetcher" / "dashboard.db"
SIM_ENGINE = BASE_DIR.parent / "v3.1-agent"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
}

# === Codes ===
WATCHLIST_CODES = [
    "600519","601398","600941","601939","601288","601857","601988","002594","300750","601318",
    "600900","601088","000858","000429","600036",
    "600406","000400","002050","601689","300308","688256","688041","600501",
]

INDEX_CODES = [
    ("s_sh000001","上证指数"),("s_sz399001","深证成指"),("s_sz399006","创业板指"),
    ("s_sh000688","科创50"),("s_sh000300","沪深300"),
]

# === DB ===
def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    return db

def ensure_tables(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS idx_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        code TEXT NOT NULL, name TEXT, price REAL, change_val REAL, change_pct REAL
    );
    CREATE TABLE IF NOT EXISTS stock_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        code TEXT NOT NULL, name TEXT, price REAL, open REAL, high REAL, low REAL,
        prev_close REAL, change_val REAL, change_pct REAL,
        volume REAL, turnover REAL
    );
    CREATE TABLE IF NOT EXISTS sector_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        name TEXT NOT NULL, change_pct REAL
    );
    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        total_assets REAL, cash REAL, market_value REAL, total_pnl REAL,
        total_pnl_pct REAL, drawdown_pct REAL, total_injected REAL
    );
    CREATE TABLE IF NOT EXISTS holding_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        code TEXT NOT NULL, name TEXT, shares INT, avg_cost REAL,
        current_price REAL, market_value REAL, pnl REAL, pnl_pct REAL,
        htype TEXT, sector TEXT
    );
    CREATE TABLE IF NOT EXISTS trade_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, action TEXT, code TEXT, name TEXT,
        shares INT, price REAL, amount REAL, commission REAL DEFAULT 5
    );
    CREATE TABLE IF NOT EXISTS analysis_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE, ts TEXT DEFAULT (datetime('now','localtime')),
        market_state TEXT, volume TEXT, up_down_ratio TEXT, state_reason TEXT,
        pelt_warnings TEXT, decisions TEXT, thoughts TEXT
    );
    CREATE TABLE IF NOT EXISTS news_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT (datetime('now','localtime')),
        source TEXT, title TEXT, url TEXT, published_at TEXT,
        UNIQUE(title, source)
    );
    CREATE INDEX IF NOT EXISTS ix_idx_ts ON idx_snapshots(ts);
    CREATE INDEX IF NOT EXISTS ix_stock_ts ON stock_snapshots(ts);
    CREATE INDEX IF NOT EXISTS ix_stock_code ON stock_snapshots(code);
    CREATE INDEX IF NOT EXISTS ix_port_ts ON portfolio_snapshots(ts);
    CREATE INDEX IF NOT EXISTS ix_hold_ts ON holding_snapshots(ts);
    """)
    db.commit()

# === Sina API ===
def fetch_sina_raw(codes):
    """codes: list of sina codes like ['sh600900','sz000400','s_sh000001']"""
    if not codes: return {}
    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        resp = s.get(url, timeout=15)
        resp.encoding = "gbk"
        results = {}
        for line in resp.text.strip().split("\n"):
            if "=" not in line: continue
            var = line.split("=")[0].strip()
            raw = var.replace("var hq_str_","")
            # strip s_ prefix for indices
            code_key = raw[2:] if raw.startswith("s_") else raw
            data_str = line.split('"')[1] if '"' in line else ""
            if not data_str: continue
            parts = data_str.split(",")
            if len(parts) < 3: continue
            is_idx = len(parts) < 10
            if is_idx:
                results[code_key] = {
                    "name":parts[0], "price":sf(parts[1]),
                    "change_val":sf(parts[2]), "change_pct":sf(parts[3]),
                    "volume":sf(parts[4]), "turnover":sf(parts[5])
                }
            else:
                results[code_key] = {
                    "name":parts[0], "open":sf(parts[1]), "prev_close":sf(parts[2]),
                    "price":sf(parts[3]), "high":sf(parts[4]), "low":sf(parts[5]),
                    "volume":sf(parts[8]), "turnover":sf(parts[9])
                }
        return results
    except Exception as e:
        print(f"  ⚠️ 新浪API: {e}")
        return {}

def sf(v):
    try: return float(v) if v else None
    except: return None

# === Tencent PE ===
def fetch_tencent_pe(codes):
    """Fetch PE(TTM) from Tencent API. Returns {code: pe_ttm}"""
    if not codes: return {}
    tencent_codes = []
    for c in codes:
        tencent_codes.append(f"sh{c}" if c.startswith(("6","68")) else f"sz{c}")
    url = f"http://qt.gtimg.cn/q={','.join(tencent_codes)}"
    try:
        s = requests.Session(); s.headers.update(HEADERS)
        resp = s.get(url, timeout=10)
        resp.encoding = 'gbk'
        result = {}
        for line in resp.text.strip().split('\n'):
            if '="' not in line: continue
            data = line.split('="')[1].rstrip('";')
            parts = data.split('~')
            if len(parts) > 39:
                raw_code = line.split('="')[0].replace('v_','')
                code = raw_code[2:] if raw_code.startswith(('sh','sz')) else raw_code
                pe = sf(parts[39])
                if pe and pe > 0: result[code] = pe
        return result
    except Exception as e:
        print(f"  ⚠️ 腾讯PE API: {e}")
        return {}

def update_pe(db, ts):
    """Fetch live PE and update latest stock_snapshots"""
    pe_data = fetch_tencent_pe(WATCHLIST_CODES)
    updated = 0
    for code, pe in pe_data.items():
        # Try to match with prefixed codes in DB
        for prefix in ['', 'sh', 'sz']:
            db.execute("UPDATE stock_snapshots SET pe_ttm=? WHERE ts=? AND code=?",
                       [pe, ts, f"{prefix}{code}" if prefix else code])
            if db.total_changes > 0: updated += 1
    if updated > 0:
        print(f"  PE更新: {updated} 只 (腾讯实时)")

# === Sectors ===
def fetch_sectors():
    """Try East Money, return empty list on failure"""
    urls = [
        "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=30&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t2&fields=f2,f3,f4,f12,f14",
    ]
    for url in urls:
        try:
            s = requests.Session(); s.headers.update(HEADERS)
            resp = s.get(url, timeout=15)
            data = resp.json()
            if data.get("rc") != 0: continue
            if data.get("data") and data["data"].get("diff"):
                return [{"name":d.get("f14",""),"change_pct":d.get("f3")} for d in data["data"]["diff"]]
        except: continue
    return None  # signal failure

# === Portfolio ===
def read_sim_state():
    sf = SIM_ENGINE / "state.json"
    if not sf.exists(): return None
    with open(sf) as f: return json.load(f)

# === Dedup helpers ===
def _check_changed(db, table, ts, key_col, key_val, fields, values):
    """Compare with previous snapshot. Returns True if changed.
    key_col=None means table has no grouping column (e.g. portfolio_snapshots)."""
    if key_col is not None:
        prev = db.execute(
            f"SELECT {','.join(fields)} FROM {table} WHERE {key_col}=? AND ts < ? ORDER BY ts DESC LIMIT 1",
            [key_val, ts]
        ).fetchone()
    else:
        prev = db.execute(
            f"SELECT {','.join(fields)} FROM {table} WHERE ts < ? ORDER BY ts DESC LIMIT 1",
            [ts]
        ).fetchone()
    if not prev:
        return True  # No previous snapshot, insert
    for f, v in zip(fields, values):
        prev_v = prev[f]
        # Float comparison with tolerance
        if isinstance(v, float) and isinstance(prev_v, (int, float)):
            if abs(v - prev_v) > 0.001:
                return True
        elif str(v) != str(prev_v):
            return True
    return False

# === Ingest ===
def ingest_indices(db, ts):
    codes = [c[0] for c in INDEX_CODES]
    name_map = {c[0].replace("s_",""): c[1] for c in INDEX_CODES}
    raw = fetch_sina_raw(codes)
    inserted = 0
    for key, d in raw.items():
        vals = [d.get("price"), d.get("change_val"), d.get("change_pct")]
        if not _check_changed(db, "idx_snapshots", ts, "code", key, ["price", "change_val", "change_pct"], vals):
            continue
        db.execute("INSERT INTO idx_snapshots(ts,code,name,price,change_val,change_pct) VALUES(?,?,?,?,?,?)",
                   [ts, key, name_map.get(key,d.get("name","")), vals[0], vals[1], vals[2]])
        inserted += 1
    print(f"  指数: {len(raw)} 抓取, {inserted} 新增")

def ingest_stocks(db, ts):
    sina_codes = []
    for c in WATCHLIST_CODES:
        sina_codes.append(f"sh{c}" if c.startswith(("6","68")) else f"sz{c}")
    raw = fetch_sina_raw(sina_codes)
    inserted = 0
    for key, d in raw.items():
        code = key
        chg = round((d.get("price") or 0) - (d.get("prev_close") or 0), 3) if d.get("price") and d.get("prev_close") else 0
        chgp = round(chg/(d["prev_close"])*100, 3) if chg and d.get("prev_close") else 0
        vals = [d.get("price"), d.get("open"), d.get("high"), d.get("low"), chg, chgp]
        if not _check_changed(db, "stock_snapshots", ts, "code", code, ["price", "open", "high", "low", "change_val", "change_pct"], vals):
            continue
        db.execute("""INSERT INTO stock_snapshots(ts,code,name,price,open,high,low,prev_close,change_val,change_pct,volume,turnover)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            [ts, code, d.get("name",""), d.get("price"), d.get("open"), d.get("high"), d.get("low"),
             d.get("prev_close"), chg, chgp, d.get("volume"), d.get("turnover")])
        inserted += 1
    print(f"  个股: {len(raw)} 抓取, {inserted} 新增")

def ingest_sectors(db, ts):
    secs = fetch_sectors()
    if secs is None:
        print(f"  板块: 抓取失败(API不可用)")
        return
    inserted = 0
    for s in secs:
        if not _check_changed(db, "sector_snapshots", ts, "name", s["name"], ["change_pct"], [s["change_pct"]]):
            continue
        db.execute("INSERT INTO sector_snapshots(ts,name,change_pct) VALUES(?,?,?)",
                   [ts, s["name"], s["change_pct"]])
        inserted += 1
    print(f"  板块: {len(secs)} 抓取, {inserted} 新增")

def ingest_portfolio(db, ts):
    state = read_sim_state()
    if not state:
        print("  持仓: 状态文件不存在")
        return
    cur = state.get("current",{})
    holdings = cur.get("holdings",{})
    trades = state.get("trades",[])
    
    total_mv = 0; total_cost = 0
    for code, h in holdings.items():
        shares = h.get("shares",0); avg = h.get("avg_cost",0)
        cost = shares * avg
        # Try live price: search both prefixed (sh600900) and clean (600900)
        row = db.execute("""
            SELECT price FROM stock_snapshots 
            WHERE code IN (?, ?, ?, ?) 
            ORDER BY ts DESC LIMIT 1
        """, [code, f"sh{code}", f"sz{code}", code]).fetchone()
        price = row["price"] if row else avg
        mv = shares * price
        pnl_pct = (price/avg-1)*100 if avg else 0
        vals = [shares, avg, price, mv, mv-cost, pnl_pct]
        if not _check_changed(db, "holding_snapshots", ts, "code", code, ["shares", "avg_cost", "current_price", "market_value", "pnl", "pnl_pct"], vals):
            total_mv += mv; total_cost += cost
            continue
        db.execute("""INSERT INTO holding_snapshots(ts,code,name,shares,avg_cost,current_price,market_value,pnl,pnl_pct,htype,sector)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            [ts, code, h.get("name",""), shares, avg, price, mv, mv-cost,
             pnl_pct, h.get("type",""), h.get("sector","")])
        total_mv += mv; total_cost += cost
    
    ta = cur.get("total_assets",100000)
    cash = cur.get("cash",89410)
    vals = [ta, cash, total_mv, total_mv-total_cost]
    if _check_changed(db, "portfolio_snapshots", ts, None, None, ["total_assets", "cash", "market_value", "total_pnl"], vals):
        db.execute("""INSERT INTO portfolio_snapshots(ts,total_assets,cash,market_value,total_pnl,total_pnl_pct,drawdown_pct,total_injected)
            VALUES(?,?,?,?,?,?,?,?)""",
            [ts, ta, cash, total_mv, total_mv-total_cost,
             (total_mv/total_cost-1)*100 if total_cost else 0,
             cur.get("drawdown_pct",0), cur.get("total_injected",0)])
    
    # Trades (idempotent)
    for t in trades:
        exists = db.execute("SELECT 1 FROM trade_log WHERE date=? AND code=? AND action=? AND shares=?",
                           [t.get("date"),t.get("code"),t.get("action"),t.get("shares")]).fetchone()
        if not exists:
            db.execute("INSERT INTO trade_log(date,action,code,name,shares,price,amount) VALUES(?,?,?,?,?,?,?)",
                       [t.get("date"),t.get("action"),t.get("code"),t.get("name"),
                        t.get("shares"),t.get("price"),t.get("amount")])
    
    print(f"  持仓: {len(holdings)} 只 | 市值: {total_mv:.0f}")

def run_analysis(db, ts, date_str):
    """Generate analysis record from latest snapshots"""
    # Market state
    indices = db.execute("SELECT * FROM idx_snapshots WHERE ts=? ORDER BY code",[ts]).fetchall()
    sh = next((i for i in indices if i["code"] in ("sh000001","000001")), None)
    pct = sh["change_pct"] if sh else 0
    
    sectors = db.execute("SELECT * FROM sector_snapshots WHERE ts=?",[ts]).fetchall()
    rising = sum(1 for s in sectors if (s["change_pct"] or 0) > 0)
    falling = len(sectors) - rising
    
    if pct > 1.0 and rising > falling*2: mode,reason = "RiskOn","指数强势+板块普涨"
    elif pct < -4.0: mode,reason = "Panic","指数暴跌"
    elif pct < -2.0 or falling > rising*2: mode,reason = "RiskOff","指数下跌+板块普跌"
    elif abs(pct) < 0.2: mode,reason = "Neutral","指数横盘"
    else: mode,reason = "Neutral","指数震荡"
    
    vol = "--"; ratio = f"{rising}涨/{falling}跌" if sectors else "--"
    
    # PELT from stock data
    stocks = db.execute("SELECT * FROM stock_snapshots WHERE ts=?",[ts]).fetchall()
    pelt = []
    for s in stocks:
        if s["change_pct"] is not None and s["change_pct"] < -5:
            pelt.append({"code":s["code"],"stock":s["name"],"warning":f"单日跌{s['change_pct']:.1f}%，触发关注"})
    
    # Holdings check
    holds = db.execute("SELECT * FROM holding_snapshots WHERE ts=?",[ts]).fetchall()
    decisions = []
    for h in holds:
        pp = h["pnl_pct"] or 0
        if pp < -8: decisions.append({"action":"🔴 止损","detail":f"{h['name']}({h['code']}) 浮亏{pp:.1f}%，触发高PE止损"})
        elif pp < -5: decisions.append({"action":"⚠️ 止损预警","detail":f"{h['name']}({h['code']}) 浮亏{pp:.1f}%"})
    if not decisions:
        decisions.append({"action":"持仓不动","detail":"所有标的在安全区间"})
    
    thoughts = f"""【市场】{mode}: {reason} | 成交额:{vol} | 涨跌比:{ratio}
【持仓】{len(holds)}只, 市值¥{sum(h['market_value'] or 0 for h in holds):.0f}
【预警】{len(pelt)}个PELT信号, {len([d for d in decisions if '止损' in d.get('action','')])}个止损信号"""
    
    db.execute("""INSERT OR REPLACE INTO analysis_log(date,ts,market_state,volume,up_down_ratio,state_reason,pelt_warnings,decisions,thoughts)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        [date_str, ts, mode, vol, ratio, reason,
         json.dumps(pelt,ensure_ascii=False), json.dumps(decisions,ensure_ascii=False), thoughts])
    
    print(f"  状态: {mode} | 预警: {len(pelt)} | 决策: {len(decisions)}")

# === Main ===
def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    hour = datetime.now().hour
    mode = sys.argv[1] if len(sys.argv) > 1 else "ingest"
    
    print(f"\n{'='*50}")
    print(f"📥 数据抓取 | {ts}")
    print(f"{'='*50}")
    
    db = get_db()
    ensure_tables(db)
    
    try:
        if mode in ("ingest", "all"):
            ingest_indices(db, ts)
            ingest_stocks(db, ts)
            update_pe(db, ts)
            ingest_sectors(db, ts)
            ingest_portfolio(db, ts)
        
        if mode in ("analysis", "all") or hour >= 15:
            print("\n📝 生成分析...")
            run_analysis(db, ts, today)
        
        db.commit()
    finally:
        db.close()
    
    print(f"\n✅ 完成 @ {ts}")

if __name__ == "__main__":
    main()