#!/usr/bin/env python3
"""Refresh A-share dashboard data from Tencent API and update all JSON files."""

import json
import urllib.request
import re
from datetime import datetime
import os

DATA_DIR = "/root/ating/portfolio/data"
STOCKS_FILE = os.path.join(DATA_DIR, "stocks.json")
INDICES_FILE = os.path.join(DATA_DIR, "indices.json")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "portfolio.json")
UPDATED_FILE = os.path.join(DATA_DIR, "updated.json")

# ── Step 1: Load stocks.json and collect all unique codes ──────────────
with open(STOCKS_FILE, "r", encoding="utf-8") as f:
    stocks_data = json.load(f)

codes_set = set()
for st in stocks_data.get("flat", []):
    codes_set.add(st["code"])
for pool in stocks_data.get("pools", []):
    for st in pool.get("stocks", []):
        codes_set.add(st["code"])

codes_list = sorted(codes_set)
print(f"Found {len(codes_list)} unique stock codes: {codes_list}")

# ── Step 2: Fetch real-time quotes from Tencent API ────────────────────
# API expects codes with sh/sz prefix, e.g. sh600036,sz300750
api_codes = ",".join(codes_list)
url = f"http://qt.gtimg.cn/q={api_codes}"
print(f"Fetching: {url}")

req = urllib.request.Request(url)
req.add_header("User-Agent", "Mozilla/5.0")
with urllib.request.urlopen(req, timeout=15) as resp:
    raw = resp.read()

# Decode GBK
text = raw.decode("gbk", errors="replace")
print(f"Response length: {len(text)} chars")

# Parse each line: v_sh600036="1~招商银行~600036~36.80~..."
# Fields: 0=market, 1=name, 2=code, 3=current_price, 4=prev_close, 5=open, 6=volume(手), 7=?, 8=?, ...
# Full format (varies):
# 0: market (1=SH, 51=SZ, etc.)
# 1: name
# 2: code (no prefix)
# 3: current_price
# 4: prev_close (昨收)
# 5: open (今开)
# 6: volume (手)
# 7: 外盘
# 8: 内盘
# 9: buy1
# 10: sell1
# 31: high
# 32: low
# 33: price/change_pct as string
# ...too many fields, let's use the standard ones

price_map = {}
for line in text.strip().split("\n"):
    line = line.strip()
    if not line or "=" not in line:
        continue
    # Extract between quotes
    m = re.search(r'"([^"]*)"', line)
    if not m:
        continue
    fields = m.group(1).split("~")
    if len(fields) < 33:
        print(f"  Skipping short line ({len(fields)} fields): {fields[:3] if len(fields)>=3 else fields}")
        continue
    
    code_no_prefix = fields[2]  # e.g. "600036"
    name = fields[1]
    current_price = float(fields[3]) if fields[3] else 0.0
    prev_close = float(fields[4]) if fields[4] else 0.0
    open_price = float(fields[5]) if fields[5] else 0.0
    volume = float(fields[6]) if fields[6] else 0.0  # 手
    high = float(fields[33]) if len(fields) > 33 and fields[33] else 0.0
    low = float(fields[34]) if len(fields) > 34 and fields[34] else 0.0
    
    # change_pct
    change_pct = round((current_price - prev_close) / prev_close * 100, 2) if prev_close else 0.0
    
    # amount (成交额, 万元) - field 37
    amount = float(fields[37]) if len(fields) > 37 and fields[37] else 0.0
    
    # turnover (换手率) - field 38
    turnover = float(fields[38]) if len(fields) > 38 and fields[38] else 0.0
    
    # PE (市盈率) - field 39
    pe = float(fields[39]) if len(fields) > 39 and fields[39] else 0.0
    
    # market_cap (总市值, 亿) - field 45
    market_cap = float(fields[45]) if len(fields) > 45 and fields[45] else 0.0
    
    price_map[code_no_prefix] = {
        "name": name,
        "price": current_price,
        "change_pct": change_pct,
        "open": open_price,
        "high": high,
        "low": low,
        "prev_close": prev_close,
        "volume": volume,
        "pe": pe,
        "amount": amount,
        "turnover": turnover,
        "market_cap": market_cap,
        "raw_code": code_no_prefix,
    }
    print(f"  {name}({code_no_prefix}): ¥{current_price:.2f} {change_pct:+.2f}%")

print(f"Parsed {len(price_map)} quotes")

# ── Step 3: Update stocks.json ────────────────────────────────────────
def update_stock_fields(st):
    """Update a stock dict with fresh price data from API."""
    code = st.get("code", "")
    # Strip sh/sz prefix for lookup
    code_no = code[2:] if code.startswith(("sh", "sz")) else code
    quote = price_map.get(code_no)
    if not quote:
        print(f"  WARNING: No quote for {code} ({code_no})")
        return False
    
    # Update price fields
    st["price"] = quote["price"]
    st["change_pct"] = quote["change_pct"]
    if "open" in st or "open" in quote:
        st["open"] = quote["open"]
    if "high" in st or "high" in quote:
        st["high"] = quote["high"]
    if "low" in st or "low" in quote:
        st["low"] = quote["low"]
    st["prev_close"] = quote["prev_close"]
    st["volume"] = quote["volume"]
    if "pe" in st or quote["pe"]:
        st["pe"] = quote["pe"]
    if "amount" in st or quote["amount"]:
        st["amount"] = quote["amount"]
    if "turnover" in st or quote["turnover"]:
        st["turnover"] = quote["turnover"]
    if "market_cap" in st or quote["market_cap"]:
        st["market_cap"] = quote["market_cap"]
    
    return True

# Update flat list
updated_flat = 0
for st in stocks_data.get("flat", []):
    if update_stock_fields(st):
        updated_flat += 1

# Update pools
updated_pools = 0
for pool in stocks_data.get("pools", []):
    for st in pool.get("stocks", []):
        if update_stock_fields(st):
            updated_pools += 1

stocks_data["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"Updated stocks: {updated_flat} flat + {updated_pools} pools = {updated_flat + updated_pools}")

# ── Step 4: Fetch index quotes ────────────────────────────────────────
index_codes = ["sh000001", "sz399001", "sz399006", "sh000688", "sh000300"]
index_names = ["上证指数", "深证成指", "创业板指", "科创50", "沪深300"]

idx_url = f"http://qt.gtimg.cn/q={','.join(index_codes)}"
print(f"Fetching indices: {idx_url}")

req = urllib.request.Request(idx_url)
req.add_header("User-Agent", "Mozilla/5.0")
with urllib.request.urlopen(req, timeout=15) as resp:
    idx_raw = resp.read()

idx_text = idx_raw.decode("gbk", errors="replace")

indices = []
for line in idx_text.strip().split("\n"):
    line = line.strip()
    if not line or "=" not in line:
        continue
    m = re.search(r'"([^"]*)"', line)
    if not m:
        continue
    fields = m.group(1).split("~")
    if len(fields) < 33:
        continue
    
    name = fields[1]
    current_price = float(fields[3]) if fields[3] else 0.0
    prev_close = float(fields[4]) if fields[4] else 0.0
    high = float(fields[33]) if len(fields) > 33 and fields[33] else 0.0
    low = float(fields[34]) if len(fields) > 34 and fields[34] else 0.0
    change_pct = round((current_price - prev_close) / prev_close * 100, 2) if prev_close else 0.0
    
    indices.append({
        "name": name,
        "code": fields[2],
        "price": current_price,
        "change_pct": change_pct,
        "high": high,
        "low": low,
    })
    print(f"  Index {name}: {current_price:.2f} {change_pct:+.2f}%")

print(f"Parsed {len(indices)} indices")

# ── Step 5: Update portfolio.json holdings ─────────────────────────────
with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
    portfolio = json.load(f)

total_market_value = 0
total_pnl = 0
up_count = 0
down_count = 0

for name, holding in portfolio.get("holdings", {}).items():
    code = holding.get("code", "")
    code_no = code[2:] if code.startswith(("sh", "sz")) else code
    quote = price_map.get(code_no)
    if not quote:
        print(f"  WARNING: No quote for holding {name} ({code})")
        continue
    
    current_price = quote["price"]
    shares = holding.get("shares", 0)
    avg_cost = holding.get("avg_cost", 0)
    cost_basis = holding.get("cost_basis", shares * avg_cost)
    
    market_value = round(current_price * shares, 2)
    pnl = round(market_value - cost_basis, 2)
    pnl_pct = round((pnl / cost_basis) * 100, 2) if cost_basis > 0 else 0.0
    
    holding["current_price"] = current_price
    holding["market_value"] = market_value
    holding["pnl"] = pnl
    holding["pnl_pct"] = pnl_pct
    
    total_market_value += market_value
    total_pnl += pnl
    
    if pnl > 0:
        up_count += 1
    elif pnl < 0:
        down_count += 1
    
    print(f"  {name}: {shares}股 × ¥{current_price} = ¥{market_value:,.2f} (P&L: ¥{pnl:+,.2f} {pnl_pct:+.2f}%)")

# Recalculate totals
cash = portfolio.get("cash", 0)
total_assets = round(cash + total_market_value, 2)
total_pnl_pct = round((total_pnl / portfolio.get("total_cost_basis", portfolio.get("cost_basis", 1))) * 100, 2) if portfolio.get("total_cost_basis") else 0.0

portfolio["market_value"] = round(total_market_value, 2)
portfolio["total_assets"] = total_assets
portfolio["pnl"] = round(total_pnl, 2)
portfolio["pnl_pct"] = total_pnl_pct
portfolio["up_count"] = up_count
portfolio["down_count"] = down_count
portfolio["total_count"] = len(portfolio.get("holdings", {}))

print(f"\nPortfolio: MV=¥{total_market_value:,.2f} Cash=¥{cash:,.2f} Total=¥{total_assets:,.2f} P&L=¥{total_pnl:+,.2f} ({total_pnl_pct:+.2f}%)")

# ── Step 6: Write all updated files ───────────────────────────────────
with open(STOCKS_FILE, "w", encoding="utf-8") as f:
    json.dump(stocks_data, f, ensure_ascii=False, indent=2)
print(f"Wrote {STOCKS_FILE}")

with open(INDICES_FILE, "w", encoding="utf-8") as f:
    json.dump(indices, f, ensure_ascii=False)
print(f"Wrote {INDICES_FILE}")

with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
    json.dump(portfolio, f, ensure_ascii=False, indent=2)
print(f"Wrote {PORTFOLIO_FILE}")

# ── Step 7: Update updated.json ───────────────────────────────────────
now = datetime.now()
updated_data = {
    "updated": now.strftime("%Y-%m-%d %H:%M:%S"),
    "date": now.strftime("%Y-%m-%d"),
    "time": now.strftime("%H:%M:%S"),
}
with open(UPDATED_FILE, "w", encoding="utf-8") as f:
    json.dump(updated_data, f, ensure_ascii=False)
print(f"Wrote {UPDATED_FILE}")

print("\n✅ Dashboard refresh complete!")