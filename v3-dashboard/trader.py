# -*- coding: utf-8 -*-
"""V3.2 自动交易执行引擎 — 模拟盘交易操作"""
import os, sys, json, time
from datetime import datetime

PORTFOLIO_PATH = os.path.expanduser("~/.hermes/portfolio/sim-portfolio.json")
TX_LOG_PATH = os.path.expanduser("~/.hermes/portfolio/transactions.log")

def load_portfolio():
    with open(PORTFOLIO_PATH) as f:
        return json.load(f)

def save_portfolio(port):
    port["updated"] = datetime.now().isoformat()
    with open(PORTFOLIO_PATH, "w") as f:
        json.dump(port, f, ensure_ascii=False, indent=2)

def log_tx(action, name, shares, price, amount, fee, category=""):
    ts = datetime.now().strftime("[%Y-%m-%d %H:%M]")
    line = f"{ts} {action} {name} {shares}股 @ ¥{price:.2f} 金额¥{amount:.2f} 手续费¥{fee:.2f}\n"
    with open(TX_LOG_PATH, "a") as f:
        f.write(line)

def buy(name, code, shares, price, category="核心仓"):
    """买入操作"""
    port = load_portfolio()
    amount = shares * price
    fee = round(amount * 0.0003, 2)  # 万三佣金
    total_cost = amount + fee
    
    cash = port.get("current_cash", 0)
    if total_cost > cash:
        return {"error": f"现金不足: 需¥{total_cost:.2f}，可用¥{cash:.2f}"}
    
    # 更新持仓
    holdings = port.get("holdings", {})
    if isinstance(holdings, dict):
        if name in holdings:
            h = holdings[name]
            old_shares = h.get("shares", 0)
            old_cost = h.get("avg_cost", 0) * old_shares
            new_shares = old_shares + shares
            h["shares"] = new_shares
            h["avg_cost"] = round((old_cost + amount) / new_shares, 4)
            h["category"] = category
        else:
            holdings[name] = {
                "shares": shares,
                "avg_cost": round(price, 4),
                "category": category,
                "code": code,
                "buy_date": datetime.now().strftime("%Y-%m-%d"),
            }
    port["holdings"] = holdings
    port["current_cash"] = round(cash - total_cost, 2)
    
    # 记录交易
    tx = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "type": "BUY",
        "name": name,
        "shares": shares,
        "price": price,
        "amount": amount,
        "fee": fee,
        "category": category,
    }
    port.setdefault("transactions", []).append(tx)
    
    save_portfolio(port)
    log_tx("买入", name, shares, price, amount, fee, category)
    
    return {"ok": True, "name": name, "shares": shares, "price": price, "total": total_cost, "cash_left": port["current_cash"]}

def sell(name, shares, price):
    """卖出操作"""
    port = load_portfolio()
    holdings = port.get("holdings", {})
    
    if isinstance(holdings, dict):
        if name not in holdings:
            return {"error": f"未持有{name}"}
        h = holdings[name]
        if shares > h.get("shares", 0):
            shares = h["shares"]  # 全部卖出
    else:
        return {"error": "持仓格式异常"}
    
    amount = shares * price
    fee = round(amount * 0.0003, 2)
    stamp_tax = round(amount * 0.001, 2)  # 千一印花税
    total_fee = fee + stamp_tax
    net_amount = amount - total_fee
    
    cost_basis = h.get("avg_cost", 0) * shares
    pnl = net_amount - cost_basis
    pnl_pct = pnl / cost_basis * 100 if cost_basis > 0 else 0
    
    # 更新持仓
    h["shares"] -= shares
    if h["shares"] <= 0:
        del holdings[name]
    port["holdings"] = holdings
    port["current_cash"] = round(port.get("current_cash", 0) + net_amount, 2)
    
    # 记录交易
    tx = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "type": "SELL",
        "name": name,
        "shares": shares,
        "price": price,
        "amount": amount,
        "fee": total_fee,
        "category": h.get("category", ""),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
    }
    port.setdefault("transactions", []).append(tx)
    
    save_portfolio(port)
    log_tx("卖出", name, shares, price, amount, total_fee, h.get("category", ""))
    
    return {"ok": True, "name": name, "shares": shares, "price": price, "net": net_amount, "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2), "cash_left": port["current_cash"]}

def get_status():
    """获取当前持仓状态"""
    port = load_portfolio()
    total_capital = port.get("initial_capital", 500000) + port.get("dca_contributed", 0)
    cash = port.get("current_cash", 0)
    holdings = port.get("holdings", {})
    
    if isinstance(holdings, dict):
        hlist = [{"name": k, **v} for k, v in holdings.items()]
    else:
        hlist = holdings
    
    return {
        "total_capital": total_capital,
        "cash": cash,
        "cash_pct": round(cash / total_capital * 100, 1) if total_capital else 0,
        "holdings_count": len([h for h in hlist if h.get("shares", 0) > 0]),
        "holdings": hlist,
        "transactions_count": len(port.get("transactions", [])),
    }

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="V3.2 交易执行")
    sub = p.add_subparsers(dest="cmd")
    
    buy_p = sub.add_parser("buy")
    buy_p.add_argument("name")
    buy_p.add_argument("code")
    buy_p.add_argument("shares", type=int)
    buy_p.add_argument("price", type=float)
    buy_p.add_argument("--category", default="核心仓")
    
    sell_p = sub.add_parser("sell")
    sell_p.add_argument("name")
    sell_p.add_argument("shares", type=int)
    sell_p.add_argument("price", type=float)
    
    sub.add_parser("status")
    
    args = p.parse_args()
    
    if args.cmd == "buy":
        r = buy(args.name, args.code, args.shares, args.price, args.category)
    elif args.cmd == "sell":
        r = sell(args.name, args.shares, args.price)
    elif args.cmd == "status":
        r = get_status()
    else:
        p.print_help()
        sys.exit(0)
    
    print(json.dumps(r, ensure_ascii=False, indent=2))
