#!/usr/bin/env python3
"""Refresh A-share stock dashboard data from Tencent API (qt.gtimg.cn)."""

import json
import urllib.request
import time
from datetime import datetime

# ── File paths ──────────────────────────────────────────────────
STOCKS_PATH = "/root/ating/portfolio/data/stocks.json"
INDICES_PATH = "/root/ating/portfolio/data/indices.json"
PORTFOLIO_PATH = "/root/ating/portfolio/data/portfolio.json"
UPDATED_PATH = "/root/ating/portfolio/data/updated.json"

# ── 1. Load stocks.json ─────────────────────────────────────────
with open(STOCKS_PATH, "r") as f:
    stocks_data = json.load(f)

# Collect all unique stock codes (strip sh/sz prefix)
all_codes = set()
for st in stocks_data["flat"]:
    all_codes.add(st["code"][2:])  # e.g. sh600900 -> 600900
for pool in stocks_data["pools"]:
    for st in pool["stocks"]:
        all_codes.add(st["code"][2:])

print(f"Total unique stock codes: {len(all_codes)}")
print(f"Codes: {sorted(all_codes)}")

# ── 2. Fetch stock quotes from Tencent API ──────────────────────
def fetch_quotes(codes, batch_size=50):
    """Fetch quotes from Tencent API. Returns dict: code -> fields list."""
    result = {}
    code_list = sorted(codes)
    for i in range(0, len(code_list), batch_size):
        batch = code_list[i:i+batch_size]
        # Build query string: sh600900,sz002594,...
        query_parts = []
        for c in batch:
            if c.startswith("6") or c.startswith("68"):
                query_parts.append(f"sh{c}")
            else:
                query_parts.append(f"sz{c}")
        query_str = ",".join(query_parts)
        url = f"http://qt.gtimg.cn/q={query_str}"
        print(f"Fetching: {url}")
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        text = raw.decode("gbk")
        # Parse lines: v_sh600900="..."
        for line in text.strip().split("\n"):
            if not line.strip() or "=" not in line:
                continue
            if '=""' in line:
                continue
            # Extract var name and value
            var_name = line.split("=")[0].strip()
            # Extract code from var name: v_sh600900 -> 600900
            code = var_name.replace("v_", "").replace("sh", "").replace("sz", "")
            # Extract the quoted value
            val = line.split('"')[1] if '"' in line else ""
            fields = val.split("~")
            result[code] = fields
        time.sleep(0.5)  # Be polite
    return result

quotes = fetch_quotes(all_codes)

# Map for quick lookup: code -> (price, change_pct, high, low, open, prev_close, volume, amount, turnover, pe, market_cap)
# Tencent API fields (0-indexed):
# 0: market, 1: name, 2: code, 3: current_price, 4: prev_close, 5: open, 6: volume(shares), 
# 7: ?, 8: ?, 9: buy1, 10: buy1_vol, ... 19: sell1, 20: sell1_vol, ...
# 30: date, 31: time, 32: change_pct, 33: high, 34: low, 35: price, 36: volume(amount), 37: turnover, 38: PE, 39: ?, 40: ?, 41: ?, 42: ?, 43: ?, 44: market_cap (in 亿), 45: total_market_cap

def parse_quote(fields):
    """Parse Tencent API fields into a dict. Returns None if invalid."""
    if len(fields) < 40:
        return None
    try:
        price = float(fields[3]) if fields[3] else 0
        prev_close = float(fields[4]) if fields[4] else 0
        open_price = float(fields[5]) if fields[5] else 0
        volume = float(fields[6]) if fields[6] else 0  # shares
        high = float(fields[33]) if len(fields) > 33 and fields[33] else 0
        low = float(fields[34]) if len(fields) > 34 and fields[34] else 0
        amount = float(fields[36]) if len(fields) > 36 and fields[36] else 0  # 万元
        turnover = float(fields[37]) if len(fields) > 37 and fields[37] else 0  # %
        pe = float(fields[38]) if len(fields) > 38 and fields[38] else 0
        market_cap = float(fields[44]) if len(fields) > 44 and fields[44] else 0  # 亿
        change_pct = (price - prev_close) / prev_close * 100 if prev_close else 0
        return {
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "prev_close": round(prev_close, 2),
            "volume": round(volume, 0),
            "amount": round(amount * 10000, 0) if amount else 0,  # convert 万元 to 元
            "turnover": round(turnover, 2),
            "pe": round(pe, 2),
            "market_cap": round(market_cap, 2),
        }
    except (ValueError, IndexError, ZeroDivisionError) as e:
        print(f"Parse error: {e} for fields: {fields[:5]}...")
        return None

# Build quote lookup
quote_map = {}
for code, fields in quotes.items():
    q = parse_quote(fields)
    if q:
        quote_map[code] = q
    else:
        print(f"WARNING: Failed to parse quote for {code}")

print(f"\nSuccessfully parsed {len(quote_map)} quotes")

# ── 3. Update stocks.json ───────────────────────────────────────
def update_stock_dict(st):
    """Update a stock dict with fresh quote data. Preserves non-price fields."""
    code_no = st["code"][2:]
    if code_no in quote_map:
        q = quote_map[code_no]
        st["price"] = q["price"]
        st["change_pct"] = q["change_pct"]
        if "open" in st:
            st["open"] = q["open"]
        if "high" in st:
            st["high"] = q["high"]
        if "low" in st:
            st["low"] = q["low"]
        if "prev_close" in st:
            st["prev_close"] = q["prev_close"]
        if "volume" in st:
            st["volume"] = q["volume"]
        if "amount" in st:
            st["amount"] = q["amount"]
        if "turnover" in st:
            st["turnover"] = q["turnover"]
        if "pe" in st:
            st["pe"] = q["pe"]
        if "market_cap" in st:
            st["market_cap"] = q["market_cap"]
    else:
        print(f"WARNING: No quote for {st['name']} ({code_no})")

# Update flat
for st in stocks_data["flat"]:
    update_stock_dict(st)

# Update pools
for pool in stocks_data["pools"]:
    for st in pool["stocks"]:
        update_stock_dict(st)

# Update timestamp
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
stocks_data["updated"] = now_str

with open(STOCKS_PATH, "w") as f:
    json.dump(stocks_data, f, ensure_ascii=False, indent=2)
print(f"\n✅ stocks.json updated ({now_str})")

# ── 4. Fetch & update indices.json ──────────────────────────────
indices_map = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
    "sh000300": "沪深300",
}

index_codes = list(indices_map.keys())
index_query = ",".join(index_codes)
index_url = f"http://qt.gtimg.cn/q={index_query}"
print(f"\nFetching indices: {index_url}")
req = urllib.request.Request(index_url)
with urllib.request.urlopen(req, timeout=15) as resp:
    raw = resp.read()
index_text = raw.decode("gbk")

with open(INDICES_PATH, "r") as f:
    indices_data = json.load(f)

for line in index_text.strip().split("\n"):
    if not line.strip() or "=" not in line or '=""' in line:
        continue
    var_name = line.split("=")[0].strip()
    val = line.split('"')[1] if '"' in line else ""
    fields = val.split("~")
    if len(fields) < 40:
        continue
    # Extract code: v_sh000001 -> sh000001
    full_code = var_name.replace("v_", "")
    code_no = full_code.replace("sh", "").replace("sz", "")
    try:
        price = float(fields[3])
        prev_close = float(fields[4])
        high = float(fields[33]) if len(fields) > 33 and fields[33] else 0
        low = float(fields[34]) if len(fields) > 34 and fields[34] else 0
        change_pct = (price - prev_close) / prev_close * 100 if prev_close else 0
    except (ValueError, IndexError, ZeroDivisionError):
        continue
    
    for idx in indices_data:
        if idx["code"] == code_no:
            idx["price"] = round(price, 2)
            idx["change_pct"] = round(change_pct, 2)
            idx["high"] = round(high, 2)
            idx["low"] = round(low, 2)
            print(f"  {idx['name']}: {idx['price']} ({idx['change_pct']:+.2f}%)")
            break

with open(INDICES_PATH, "w") as f:
    json.dump(indices_data, f, ensure_ascii=False)
print(f"✅ indices.json updated")

# ── 5. Update portfolio.json ────────────────────────────────────
with open(PORTFOLIO_PATH, "r") as f:
    portfolio = json.load(f)

# Build code->price lookup from fresh quotes
price_lookup = {}
for code, q in quote_map.items():
    price_lookup[code] = q["price"]

total_market_value = 0
total_cost = portfolio.get("total_cost_basis", 0)
holdings = portfolio.get("holdings", {})

for name, h in holdings.items():
    code = h.get("code", "")
    code_no = code[2:] if code else ""
    if code_no in price_lookup:
        new_price = price_lookup[code_no]
        h["current_price"] = new_price
        shares = h.get("shares", 0)
        h["market_value"] = round(new_price * shares, 2)
        avg_cost = h.get("avg_cost", 0)
        cost_basis = h.get("cost_basis", avg_cost * shares)
        h["pnl"] = round(h["market_value"] - cost_basis, 2)
        if cost_basis > 0:
            h["pnl_pct"] = round((h["market_value"] - cost_basis) / cost_basis * 100, 2)
        else:
            h["pnl_pct"] = 0
        total_market_value += h["market_value"]
        print(f"  {name}: {new_price} (shares={shares}, mv={h['market_value']}, pnl={h['pnl']})")
    else:
        total_market_value += h.get("market_value", 0)
        print(f"  {name}: NO PRICE UPDATE (code={code_no})")

# Recalculate totals
cash = portfolio.get("cash", 0)
total_assets = round(cash + total_market_value, 2)
portfolio["market_value"] = round(total_market_value, 2)
portfolio["total_assets"] = total_assets
portfolio["pnl"] = round(total_assets - portfolio.get("initial_principal", 0), 2)
if portfolio.get("initial_principal", 0) > 0:
    portfolio["pnl_pct"] = round(
        (total_assets - portfolio["initial_principal"]) / portfolio["initial_principal"] * 100, 2
    )
else:
    portfolio["pnl_pct"] = 0

# Recalculate total invested and cost basis
total_cost_basis = sum(h.get("cost_basis", h.get("avg_cost", 0) * h.get("shares", 0)) for h in holdings.values())
portfolio["total_cost_basis"] = round(total_cost_basis, 2)

print(f"\nPortfolio summary:")
print(f"  Cash: ¥{cash:,.2f}")
print(f"  Market Value: ¥{total_market_value:,.2f}")
print(f"  Total Assets: ¥{total_assets:,.2f}")
print(f"  P&L: ¥{portfolio['pnl']:,.2f} ({portfolio['pnl_pct']:+.2f}%)")

with open(PORTFOLIO_PATH, "w") as f:
    json.dump(portfolio, f, ensure_ascii=False, indent=2)
print(f"✅ portfolio.json updated")

# ── 6. Update updated.json ──────────────────────────────────────
now = datetime.now()
updated = {
    "updated": now.strftime("%Y-%m-%d %H:%M:%S"),
    "date": now.strftime("%Y-%m-%d"),
    "time": now.strftime("%H:%M:%S"),
}
with open(UPDATED_PATH, "w") as f:
    json.dump(updated, f, ensure_ascii=False)
print(f"✅ updated.json: {updated['updated']}")

print("\n🎉 All data refreshed successfully!")