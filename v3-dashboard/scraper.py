# -*- coding: utf-8 -*-
"""V3.1 Dashboard — 数据采集器。东方财富 API → SQLite。"""
import os, sys, json, time, urllib.request, urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from db import get_db, init_db, export_all_json

# ── 代理配置 ──
PROXY = "http://127.0.0.1:7897"

# ── 自选股列表 (code, market, name) ──
WATCHLIST = [
    ("000858", 0, "五粮液"), ("601088", 1, "中国神华"), ("000429", 0, "粤高速A"),
    ("600941", 1, "中国移动"), ("601398", 1, "工商银行"), ("601689", 0, "拓普集团"),
    ("002050", 0, "三花智控"), ("600519", 1, "贵州茅台"), ("600900", 1, "长江电力"),
    ("600436", 1, "片仔癀"),   ("688256", 1, "寒武纪"),   ("300308", 0, "中际旭创"),
    ("688041", 1, "海光信息"), ("600406", 1, "国电南瑞"), ("000400", 0, "许继电气"),
    ("600391", 1, "航天晨光"), ("003031", 0, "江顺科技"),
    ("002594", 0, "比亚迪"),
]

MARKET_NAMES = {"1.000001": "上证指数", "0.399001": "深证成指", "0.399006": "创业板指"}


def _fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"
    })
    proxy = urllib.request.ProxyHandler({"https": PROXY, "http": PROXY})
    opener = urllib.request.build_opener(proxy)
    with opener.open(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect_market(conn):
    """拉取三大指数。"""
    print("📊 大盘指数...", end=" ")
    url = "https://push2.eastmoney.com/api/qt/ulist.np?fltt=2&fields=f2,f3,f6,f15,f16,f17,f18&secids=1.000001,0.399001,0.399006"
    data = _fetch(url)
    rows = data.get("data", {}).get("diff", [])
    for r in rows:
        secid = r.get("f12", "")
        conn.execute("""
            INSERT INTO market_index (name, code, price, change_pct, volume, high, low, open, prev_close)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            MARKET_NAMES.get(secid, secid), secid,
            _div(r, "f2"), _div(r, "f3"),
            r.get("f6"), _div(r, "f15"), _div(r, "f16"), _div(r, "f17"), _div(r, "f18"),
        ))
    conn.commit()
    print(f"{len(rows)}条 ✓")


def collect_stocks(conn):
    """拉取所有自选股行情。"""
    print("📈 个股行情...", end=" ")
    mkt_map = {0: "0", 1: "1"}
    count = 0
    for code, mkt, name in WATCHLIST:
        try:
            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={mkt_map[mkt]}.{code}&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f60,f116,f117,f162,f167,f168,f169,f170,f171"
            d = _fetch(url).get("data", {})
            if not d: continue
            conn.execute("""
                INSERT INTO stock_price (code,name,price,change_pct,change_amt,volume,turnover,high,low,open,prev_close,pe)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                f"{mkt_map[mkt]}.{code}", name,
                _div(d, "f43"), _div(d, "f170"), _div(d, "f169"),
                d.get("f47"), d.get("f48"),
                _div(d, "f44"), _div(d, "f45"), _div(d, "f46"), _div(d, "f60"),
                _div(d, "f162"),
            ))
            count += 1
            time.sleep(0.12)
        except Exception as e:
            print(f"\n   ⚠️ {name}: {e}")
    conn.commit()
    print(f"{count}只 ✓")


def collect_portfolio(conn):
    """保存持仓快照。"""
    try:
        with open(os.path.expanduser("~/.hermes/portfolio/sim-portfolio.json")) as f:
            port = json.load(f)
    except Exception:
        return
    hlist = port.get("holdings", [])
    cash = float(port.get("cash", 0))
    mv = sum((h.get("current_price") or 0) * (h.get("shares") or 0) for h in hlist)
    total = cash + mv
    profit = total - 100000
    cat_mv = {"现金牛": 0, "成长股": 0, "拓荒型": 0}
    for h in hlist:
        cat_mv[h.get("category", "")] = cat_mv.get(h.get("category", ""), 0) + (h.get("current_price") or 0) * (h.get("shares") or 0)
    conn.execute("""
        INSERT INTO portfolio_snapshot (total_asset,total_profit,total_profit_pct,cash,cash_cow_pct,growth_pct,frontier_pct)
        VALUES (?,?,?,?,?,?,?)
    """, (round(total,2), round(profit,2), round(profit/100000*100,2) if total>0 else 0,
          round(cash,2),
          round(cat_mv["现金牛"]/total*100,1) if total>0 else 0,
          round(cat_mv["成长股"]/total*100,1) if total>0 else 0,
          round(cat_mv["拓荒型"]/total*100,1) if total>0 else 0))
    conn.commit()
    print(f"💰 持仓快照 ✓")


def _div(d, k):
    v = d.get(k)
    return v / 100 if v is not None else None


def main():
    init_db()
    conn = get_db()
    try:
        collect_market(conn)
        collect_stocks(conn)
        collect_portfolio(conn)
        export_all_json()
        print("✅ 采集完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()