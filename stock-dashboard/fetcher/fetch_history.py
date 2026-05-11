#!/usr/bin/env python3
"""批量拉取自选股2年日K/周K数据 → data/history/{code}.json
数据源: 新浪财经 (历史K线) + 东方财富 (备选)
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_DIR = BASE_DIR / "data" / "history"
WATCHLIST_FILE = BASE_DIR / "data" / "watchlist.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
}

def code_to_sina(code):
    """Convert to sina prefix"""
    if code.startswith("6") or code.startswith("68"):
        return f"sh{code}"
    return f"sz{code}"

def fetch_sina_daily(code):
    """Fetch daily K-line from Sina (up to ~2000 trading days)"""
    sina = code_to_sina(code)
    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {
        "symbol": sina,
        "scale": "240",  # daily
        "ma": "no",
        "datalen": "500",  # ~2 years
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        data = resp.json()
        if not data or not isinstance(data, list):
            return []
        
        klines = []
        for d in data:
            klines.append({
                "date": d.get("day", ""),
                "open": float(d.get("open", 0)),
                "close": float(d.get("close", 0)),
                "high": float(d.get("high", 0)),
                "low": float(d.get("low", 0)),
                "volume": float(d.get("volume", 0)),
            })
        return klines
    except Exception as e:
        print(f"  ⚠️ 新浪日K失败: {e}")
        return []

def fetch_sina_weekly(code):
    """Fetch weekly K-line from Sina"""
    sina = code_to_sina(code)
    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {
        "symbol": sina,
        "scale": "1200",  # weekly
        "ma": "no",
        "datalen": "120",
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        data = resp.json()
        if not data or not isinstance(data, list):
            return []
        
        klines = []
        for d in data:
            klines.append({
                "date": d.get("day", ""),
                "open": float(d.get("open", 0)),
                "close": float(d.get("close", 0)),
                "high": float(d.get("high", 0)),
                "low": float(d.get("low", 0)),
                "volume": float(d.get("volume", 0)),
            })
        return klines
    except Exception as e:
        print(f"  ⚠️ 新浪周K失败: {e}")
        return []

def fetch_eastmoney_kline(code, klt=101, lmt=500):
    """Fallback: East Money K-line"""
    if code.startswith("6") or code.startswith("68"):
        secid = f"1.{code}"
    else:
        secid = f"0.{code}"
    
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "klt": klt,
        "fqt": "1",
        "end": "20500101",
        "lmt": lmt,
    }
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        resp = s.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("data") and data["data"].get("klines"):
            klines = []
            for line in data["data"]["klines"]:
                parts = line.split(",")
                if len(parts) >= 7:
                    klines.append({
                        "date": parts[0],
                        "open": float(parts[1]),
                        "close": float(parts[2]),
                        "high": float(parts[3]),
                        "low": float(parts[4]),
                        "volume": float(parts[5]),
                    })
            return klines
    except Exception:
        pass
    return []

def save_stock_history(code):
    """Fetch and save history for one stock"""
    # Try Sina first
    daily = fetch_sina_daily(code)
    weekly = fetch_sina_weekly(code)
    
    # Fallback to East Money if Sina returns too little
    if len(daily) < 50:
        daily_em = fetch_eastmoney_kline(code, 101, 500)
        if len(daily_em) > len(daily):
            daily = daily_em
    
    if len(weekly) < 10:
        weekly_em = fetch_eastmoney_kline(code, 102, 120)
        if len(weekly_em) > len(weekly):
            weekly = weekly_em
    
    if not daily and not weekly:
        return False
    
    data = {
        "code": code,
        "daily": daily,
        "weekly": weekly,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_DIR / f"{code}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    
    return True

def load_watchlist_codes():
    if not WATCHLIST_FILE.exists():
        return []
    with open(WATCHLIST_FILE) as f:
        data = json.load(f)
    return [s["code"] for s in data.get("stocks", [])]

def main():
    codes = load_watchlist_codes()
    if not codes:
        print("⚠️ 没有自选股数据")
        return
    
    print(f"📊 拉取 {len(codes)} 只自选股历史K线 (新浪+东方财富)\n")
    
    success = 0
    for i, code in enumerate(codes):
        print(f"  [{i+1}/{len(codes)}] {code}...", end=" ", flush=True)
        if save_stock_history(code):
            path = HISTORY_DIR / f"{code}.json"
            with open(path) as f:
                d = json.load(f)
            dc = len(d.get("daily", []))
            wc = len(d.get("weekly", []))
            print(f"✅ 日K:{dc}条 周K:{wc}条")
            success += 1
        else:
            print("❌ 失败")
        
        time.sleep(0.5)  # Rate limit
    
    print(f"\n✅ 完成: {success}/{len(codes)} 只成功")

if __name__ == "__main__":
    main()