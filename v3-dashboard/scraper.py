# -*- coding: utf-8 -*-
"""V3.1 Dashboard — 数据采集器。新浪 API → SQLite（增量写入）。"""
import os, sys, json, time, urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from db import get_db, init_db, export_all_json

# ── 自选股列表 (code, name) ──
# 代码自动识别市场：6开头=上海(sh), 0/3开头=深圳(sz)
WATCHLIST = [
    ("000858", "五粮液"),   ("601088", "中国神华"), ("000429", "粤高速A"),
    ("600941", "中国移动"), ("601398", "工商银行"), ("601689", "拓普集团"),
    ("002050", "三花智控"), ("600519", "贵州茅台"), ("600900", "长江电力"),
    ("600436", "片仔癀"),   ("688256", "寒武纪"),   ("300308", "中际旭创"),
    ("688041", "海光信息"), ("600406", "国电南瑞"), ("000400", "许继电气"),
    ("600391", "航天晨光"), ("003031", "江顺科技"), ("002594", "比亚迪"),
    ("300750", "宁德时代"), ("601318", "中国平安"),
    ("600036", "招商银行"), ("000333", "美的集团"), ("600276", "恒瑞医药"),
]

# ── 指数映射 ──
SINA_INDICES = [
    ("s_sh000001", "1.000001", "上证指数"),
    ("s_sz399001", "0.399001", "深证成指"),
    ("s_sz399006", "0.399006", "创业板指"),
]


def _sina_code(code):
    """600519 → sh600519, 000858 → sz000858"""
    return ("sh" if code.startswith(("6", "68")) else "sz") + code


def _fetch_sina(codes):
    """请求新浪 API，返回 {code: {name,price,...}}"""
    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        text = resp.read().decode("gbk")

    results = {}
    for line in text.strip().split("\n"):
        if "=" not in line:
            continue
        raw_key = line.split("=")[0].replace("var hq_str_", "").strip()
        data_str = line.split('"')[1] if '"' in line else ""
        parts = data_str.split(",")
        if len(parts) < 4:
            continue

        # 判断是指数还是个股：指数 parts[4] 是成交量(手)，个股 parts[1] 是开盘价
        is_index = raw_key.startswith("s_")
        if is_index:
            results[raw_key] = {
                "name": parts[0],
                "price": _sf(parts[1]),
                "change_val": _sf(parts[2]),
                "change_pct": _sf(parts[3]),
                "volume": _sf(parts[4], 100),  # 手→股
                "turnover": _sf(parts[5]),
            }
        else:
            results[raw_key] = {
                "name": parts[0],
                "open": _sf(parts[1]),
                "prev_close": _sf(parts[2]),
                "price": _sf(parts[3]),
                "high": _sf(parts[4]),
                "low": _sf(parts[5]),
                "volume": _sf(parts[8]),
                "turnover": _sf(parts[9]),
            }
    return results


def _sf(val, multiplier=1):
    """Safe float parser，失败返回 None。"""
    try:
        return float(val) * multiplier if val else None
    except (ValueError, TypeError):
        return None


def collect_market(conn):
    """拉取三大指数（新浪 API）。"""
    print("📊 大盘指数...", end=" ")
    codes = [c for c, _, _ in SINA_INDICES]
    data = _fetch_sina(codes)
    count = 0
    for sina_code, em_code, name in SINA_INDICES:
        d = data.get(sina_code)
        if not d:
            continue
        price = d["price"]
        change_pct = d["change_pct"]
        prev_close = round(price / (1 + change_pct / 100), 2) if price and change_pct else None
        conn.execute("""
            INSERT INTO market_index (name, code, price, change_pct, volume, high, low, open, prev_close)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (name, em_code, price, change_pct, d.get("volume"),
              None, None, None, prev_close))
        count += 1
    conn.commit()
    print(f"{count}条 ✓")


def collect_stocks(conn):
    """批量拉取自选股行情（新浪 API，分批 10 只/批）。"""
    print("📈 个股行情...", end=" ")
    BATCH = 10
    count = 0
    items = [(code, name, _sina_code(code)) for code, name in WATCHLIST]
    for i in range(0, len(items), BATCH):
        batch = items[i:i + BATCH]
        sina_codes = [s for _, _, s in batch]
        try:
            data = _fetch_sina(sina_codes)
        except Exception as e:
            print(f"\n   ⚠️ batch {i//BATCH+1} 拉取失败: {e}")
            continue

        for code, name, sina_code in batch:
            d = data.get(sina_code)
            if not d:
                print(f"\n   ⚠️ {name} 无数据")
                continue
            em_code = _sina_code(code).replace("sh", "1.").replace("sz", "0.")
            conn.execute("""
                INSERT INTO stock_price (code,name,price,change_pct,change_amt,volume,turnover,high,low,open,prev_close,pe)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                em_code, name,
                d["price"],
                round((d["price"] - d["prev_close"]) / d["prev_close"] * 100, 2) if d.get("price") and d.get("prev_close") else None,
                round(d["price"] - d["prev_close"], 2) if d.get("price") and d.get("prev_close") else None,
                d.get("volume"), d.get("turnover"),
                d.get("high"), d.get("low"), d.get("open"), d.get("prev_close"),
                None,  # PE 新浪不提供
            ))
            count += 1
        time.sleep(0.3)  # 批次间限流
    conn.commit()
    print(f"{count}只 ✓")


def collect_portfolio(conn):
    """保存持仓快照。"""
    try:
        with open(os.path.expanduser("~/.hermes/portfolio/sim-portfolio.json")) as f:
            port = json.load(f)
    except Exception:
        print("💰 持仓: 无文件")
        return

    # holdings 可能是 dict(按名称索引) 或 list
    raw = port.get("holdings", {})
    if isinstance(raw, dict):
        hlist = list(raw.values())
    elif isinstance(raw, list):
        hlist = raw
    else:
        print("💰 持仓: 格式未知")
        return

    cash = float(port.get("current_cash", port.get("cash", 0)))
    mv = sum((h.get("current_price") or h.get("avg_cost") or 0) * (h.get("shares") or 0) for h in hlist)
    total = cash + mv
    profit = total - 100000

    cat_mv = {"现金牛": 0, "成长股": 0, "拓荒型": 0}
    for h in hlist:
        cat = h.get("category", "")
        cat_mv[cat] = cat_mv.get(cat, 0) + (h.get("current_price") or h.get("avg_cost") or 0) * (h.get("shares") or 0)

    conn.execute("""
        INSERT INTO portfolio_snapshot (total_asset,total_profit,total_profit_pct,cash,cash_cow_pct,growth_pct,frontier_pct)
        VALUES (?,?,?,?,?,?,?)
    """, (round(total, 2), round(profit, 2),
          round(profit / 100000 * 100, 2) if total > 0 else 0,
          round(cash, 2),
          round(cat_mv.get("现金牛", 0) / total * 100, 1) if total > 0 else 0,
          round(cat_mv.get("成长股", 0) / total * 100, 1) if total > 0 else 0,
          round(cat_mv.get("拓荒型", 0) / total * 100, 1) if total > 0 else 0))
    conn.commit()
    print(f"💰 持仓快照 ✓")


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