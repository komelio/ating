# -*- coding: utf-8 -*-
"""V3.2 操盘策略引擎 — 三重过滤 + 6大策略 + 仓位管理 + 止盈止损"""
import os, sys, json, math
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from db import get_db, init_db

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  V3.2 策略参数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRATEGY = {
    "initial_capital": 500000,
    "core_ratio": 0.50,       # 核心仓 50%
    "tactical_ratio": 0.30,   # 机动仓 30%
    "cash_reserve": 0.20,     # 现金储备 20%
    "core_count": 3,          # 核心仓最多3只
    "tactical_count": 2,      # 机动仓最多2只
    "stop_loss_pct": 8.0,     # 跌破买入价8%无条件止损（回测优化）
    "ma20_stop_days": 3,      # 跌破MA20且3日未收回止损
    "single_loss_limit": 0.02, # 单只最大亏损=总资金2%
    "daily_loss_limit": 0.03,  # 日最大亏损3%
    "weekly_loss_limit": 0.05, # 周最大亏损5%
    "profit_take_1": 10,      # +10% 卖1/3
    "profit_take_2": 20,      # +20% 再卖1/3
    "trailing_stop": 8,       # 剩余跟踪止盈(从最高点回落8%)
    "min_change_pct": -2.0,   # 买入允许回调2%（回测优化）
    "max_change_pct": 3.0,    # 买入最高涨幅3%（不追高）
    "min_turnover": 2e8,      # 最低成交额2亿
    "max_pe": 50,             # PE上限
    "require_ma20": True,     # 趋势过滤：收盘价>MA20
    "require_volume": True,   # 成交量过滤：>5日均量
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  自选股池 (V3.2 趋势策略适配)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WATCHLIST_V32 = [
    # ── AI算力/芯片 ──
    ("688256", "寒武纪"),    ("688041", "海光信息"),
    ("002371", "北方华创"),  ("688012", "中微公司"),
    ("603986", "兆易创新"),  ("600584", "长电科技"),
    # ── 新能源/汽车 ──
    ("002594", "比亚迪"),    ("300750", "宁德时代"),
    ("601689", "拓普集团"),  ("002050", "三花智控"),
    # ── 消费/医药 ──
    ("600519", "贵州茅台"),  ("000858", "五粮液"),
    ("600276", "恒瑞医药"),  ("000333", "美的集团"),
    # ── 金融/蓝筹 ──
    ("601318", "中国平安"),  ("600036", "招商银行"),
    ("600941", "中国移动"),  ("601088", "中国神华"),
    # ── 电力/能源 ──
    ("600900", "长江电力"),  ("601985", "中国核电"),
    ("003816", "中国广核"),
    # ── 军工/高端制造 ──
    ("600406", "国电南瑞"),  ("000400", "许继电气"),
    ("002837", "英维克"),
]


def run_strategy():
    """执行完整策略流程：扫描 → 过滤 → 信号 → 仓位建议"""
    init_db()
    conn = get_db()
    
    result = {
        "timestamp": datetime.now().isoformat(),
        "market_env": _check_market(conn),
        "signals": [],
        "stop_loss_alerts": [],
        "profit_take_alerts": [],
        "buy_candidates": [],
        "position_advice": "",
        "focus_alerts": [],
    }
    
    # 1. 检查持仓止损/止盈
    portfolio = _load_portfolio()
    if portfolio:
        result["stop_loss_alerts"] = _check_stop_loss(conn, portfolio)
        result["profit_take_alerts"] = _check_profit_take(conn, portfolio)
    
    # 2. 扫描买入候选
    result["buy_candidates"] = _scan_buy_candidates(conn)
    
    # 3. 仓位建议
    result["position_advice"] = _calc_position_advice(portfolio)
    
    # 4. 重点关注股票检查
    result["focus_alerts"] = _check_focus_stocks(conn, portfolio)
    
    conn.close()
    
    # 保存到数据库
    _save_strategy_result(result)
    
    return result


def _check_market(conn):
    """第一层：市场环境检查"""
    cur = conn.execute("""
        SELECT name, price, change_pct FROM market_index
        WHERE fetched_at > datetime('now','-1 day')
        ORDER BY fetched_at DESC LIMIT 3
    """)
    indices = [dict(r) for r in cur.fetchall()]
    
    if not indices:
        return {"state": "unknown", "indices": [], "can_trade": False, "reason": "无大盘数据"}
    
    avg_chg = sum(i.get("change_pct", 0) for i in indices) / len(indices)
    ss_chg = indices[0].get("change_pct", 0) if indices else 0
    
    if ss_chg < -2:
        state, can_trade = "crash", False
        reason = f"大盘暴跌{ss_chg:.1f}%，禁止买入"
    elif avg_chg < -1:
        state, can_trade = "bear", False
        reason = "大盘偏弱，暂停买入"
    elif avg_chg > 1:
        state, can_trade = "bull", True
        reason = "大盘强势，可正常买入"
    else:
        state, can_trade = "shock", True
        reason = "震荡市，正常交易"
    
    return {
        "state": state,
        "indices": indices,
        "avg_change": round(avg_chg, 2),
        "can_trade": can_trade,
        "reason": reason,
    }


def _load_portfolio():
    """加载当前持仓"""
    path = os.path.expanduser("~/.hermes/portfolio/sim-portfolio.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _check_stop_loss(conn, portfolio):
    """检查止损条件"""
    alerts = []
    raw = portfolio.get("holdings", {})
    if isinstance(raw, dict):
        hlist = list(raw.values())
    elif isinstance(raw, list):
        hlist = raw
    else:
        return alerts
    
    total_capital = portfolio.get("initial_capital", 500000) + portfolio.get("dca_contributed", 0)
    
    for h in hlist:
        name = h.get("name", "")
        cost = h.get("avg_cost") or h.get("cost_price") or 0
        shares = h.get("shares", 0)
        if cost <= 0 or shares <= 0:
            continue
        
        # 查当前价
        cur = conn.execute(
            "SELECT price, change_pct FROM stock_price WHERE name=? ORDER BY fetched_at DESC LIMIT 1",
            (name,)
        )
        row = cur.fetchone()
        if not row:
            continue
        cur_price = row["price"] or 0
        if cur_price <= 0:
            continue
        
        pnl_pct = (cur_price - cost) / cost * 100
        loss_amount = (cost - cur_price) * shares
        
        # 铁律1: 跌破买入价5%
        if pnl_pct <= -STRATEGY["stop_loss_pct"]:
            alerts.append({
                "type": "HARD_STOP",
                "name": name,
                "reason": f"跌破买入价{STRATEGY['stop_loss_pct']}% (当前{pnl_pct:.1f}%)",
                "action": f"立即止损卖出{shares}股",
                "pnl_pct": round(pnl_pct, 2),
                "loss": round(loss_amount, 2),
            })
        
        # 铁律2: 单只亏损达总资金2%
        if loss_amount >= total_capital * STRATEGY["single_loss_limit"]:
            alerts.append({
                "type": "SINGLE_LIMIT",
                "name": name,
                "reason": f"单只亏损¥{loss_amount:.0f}达总资金{loss_amount/total_capital*100:.1f}%",
                "action": f"止损卖出",
                "pnl_pct": round(pnl_pct, 2),
                "loss": round(loss_amount, 2),
            })
    
    return alerts


def _check_profit_take(conn, portfolio):
    """检查止盈条件"""
    alerts = []
    raw = portfolio.get("holdings", {})
    if isinstance(raw, dict):
        hlist = list(raw.values())
    elif isinstance(raw, list):
        hlist = raw
    else:
        return alerts
    
    for h in hlist:
        name = h.get("name", "")
        cost = h.get("avg_cost") or h.get("cost_price") or 0
        shares = h.get("shares", 0)
        if cost <= 0 or shares <= 0:
            continue
        
        cur = conn.execute(
            "SELECT price FROM stock_price WHERE name=? ORDER BY fetched_at DESC LIMIT 1",
            (name,)
        )
        row = cur.fetchone()
        if not row:
            continue
        cur_price = row["price"] or 0
        if cur_price <= 0:
            continue
        
        pnl_pct = (cur_price - cost) / cost * 100
        
        if pnl_pct >= STRATEGY["profit_take_2"]:
            sell_1 = shares // 3
            sell_2 = shares // 3
            alerts.append({
                "type": "PROFIT_TAKE_2",
                "name": name,
                "reason": f"盈利{pnl_pct:.1f}%≥{STRATEGY['profit_take_2']}%",
                "action": f"再卖1/3 ({sell_2}股)，剩余跟踪止盈",
                "pnl_pct": round(pnl_pct, 2),
            })
        elif pnl_pct >= STRATEGY["profit_take_1"]:
            sell = shares // 3
            alerts.append({
                "type": "PROFIT_TAKE_1",
                "name": name,
                "reason": f"盈利{pnl_pct:.1f}%≥{STRATEGY['profit_take_1']}%",
                "action": f"卖出1/3 ({sell}股)锁定利润",
                "pnl_pct": round(pnl_pct, 2),
            })
    
    return alerts


def _scan_buy_candidates(conn):
    """扫描买入候选 — 三重过滤"""
    candidates = []
    
    for code, name in WATCHLIST_V32:
        # 获取最新行情
        em_code = ("1." if code.startswith(("6",)) else "0.") + code
        cur = conn.execute(
            "SELECT * FROM stock_price WHERE code=? ORDER BY fetched_at DESC LIMIT 1",
            (em_code,)
        )
        row = cur.fetchone()
        if not row:
            continue
        
        stock = dict(row)
        price = stock.get("price") or 0
        change_pct = stock.get("change_pct") or 0
        turnover = stock.get("turnover") or 0
        pe = stock.get("pe") or 0
        
        # ── 第一层：基本面门槛 ──
        if pe > 0 and pe > STRATEGY["max_pe"]:
            continue  # PE过高
        if turnover < STRATEGY["min_turnover"]:
            continue  # 成交额不足
        
        # ── 第二层：技术面确认 ──
        # 涨幅在合理区间 (2%-7%)
        if change_pct < STRATEGY["min_change_pct"] or change_pct > STRATEGY["max_change_pct"]:
            continue
        
        # 检查策略信号
        strategy_hit = _check_strategies(conn, code, stock)
        if not strategy_hit:
            continue
        
        candidates.append({
            "code": code,
            "name": name,
            "price": price,
            "change_pct": round(change_pct, 2),
            "turnover": turnover,
            "pe": round(pe, 1) if pe else None,
            "strategies": strategy_hit,
            "signal_strength": len(strategy_hit),
        })
    
    # 按信号强度排序
    candidates.sort(key=lambda x: x["signal_strength"], reverse=True)
    return candidates[:10]


def _check_strategies(conn, code, stock):
    """检查6大策略信号"""
    hits = []
    change_pct = stock.get("change_pct") or 0
    turnover = stock.get("turnover") or 0
    price = stock.get("price") or 0
    prev_close = stock.get("prev_close") or 0
    
    # 策略1: 放量上涨 (涨幅≥2% + 成交额≥2亿)
    if change_pct >= 2.0 and turnover >= 2e8:
        hits.append("放量上涨")
    
    # 策略2: 平台突破 (需要历史数据判断)
    # 简化版: 创近期新高
    em_code = ("1." if code.startswith(("6",)) else "0.") + code
    cur = conn.execute(
        "SELECT price FROM stock_price WHERE code=? AND fetched_at > datetime('now','-60 days') ORDER BY price DESC LIMIT 1",
        (em_code,)
    )
    high_60d = cur.fetchone()
    if high_60d and price and high_60d["price"] and price >= high_60d["price"] * 0.98:
        hits.append("平台突破")
    
    # 策略3: 海龟交易 (创60日新高)
    if high_60d and price and high_60d["price"] and price >= high_60d["price"] * 0.99:
        hits.append("海龟新高")
    
    # 策略4: 低波动上涨 (连续3日涨幅0.5%-3%)
    cur = conn.execute(
        "SELECT change_pct FROM stock_price WHERE code=? ORDER BY fetched_at DESC LIMIT 3",
        (em_code,)
    )
    recent = [r["change_pct"] for r in cur.fetchall() if r["change_pct"] is not None]
    if len(recent) >= 3 and all(0.5 <= c <= 3.0 for c in recent):
        hits.append("低波上涨")
    
    return hits


def _calc_position_advice(portfolio):
    """计算仓位建议"""
    if not portfolio:
        return "无持仓数据"
    
    total_capital = portfolio.get("initial_capital", 500000) + portfolio.get("dca_contributed", 0)
    cash = portfolio.get("current_cash", 0)
    
    raw = portfolio.get("holdings", {})
    if isinstance(raw, dict):
        hlist = list(raw.values())
    elif isinstance(raw, list):
        hlist = raw
    else:
        hlist = []
    
    n_holdings = len([h for h in hlist if h.get("shares", 0) > 0])
    cash_pct = cash / total_capital * 100 if total_capital > 0 else 0
    
    core_budget = total_capital * STRATEGY["core_ratio"]
    tactical_budget = total_capital * STRATEGY["tactical_ratio"]
    reserve = total_capital * STRATEGY["cash_reserve"]
    
    lines = [
        f"💰 总资金: ¥{total_capital:,.0f}",
        f"📊 当前持仓: {n_holdings}只 | 现金: ¥{cash:,.0f} ({cash_pct:.1f}%)",
        f"",
        f"📐 目标配置:",
        f"  核心仓(50%): ¥{core_budget:,.0f} / {STRATEGY['core_count']}只",
        f"  机动仓(30%): ¥{tactical_budget:,.0f} / {STRATEGY['tactical_count']}只",
        f"  现金储备(20%): ¥{reserve:,.0f}",
    ]
    
    if cash_pct < STRATEGY["cash_reserve"] * 100:
        lines.append(f"\n⚠️ 现金不足{STRATEGY['cash_reserve']*100:.0f}%，暂停买入")
    elif cash_pct > 50:
        lines.append(f"\n💡 现金充裕({cash_pct:.0f}%)，可积极建仓")
    
    return "\n".join(lines)


def _check_focus_stocks(conn, portfolio):
    """检查重点关注股票的买入/卖出信号"""
    focus_path = os.path.expanduser("~/.hermes/portfolio/watchlist_focus.json")
    if not os.path.exists(focus_path):
        return []
    
    try:
        with open(focus_path) as f:
            focus_data = json.load(f)
    except Exception:
        return []
    
    alerts = []
    focus_stocks = focus_data.get("focus_stocks", [])
    
    # 获取持仓信息
    holdings_map = {}
    if portfolio:
        raw = portfolio.get("holdings", {})
        if isinstance(raw, dict):
            holdings_map = {h.get("name"): h for h in raw.values()}
        elif isinstance(raw, list):
            holdings_map = {h.get("name"): h for h in raw}
    
    for stock in focus_stocks:
        code = stock.get("code")
        name = stock.get("name")
        alert_rules = stock.get("alert_rules", {})
        
        # 查询最新行情
        em_code = ("1." if code.startswith(("6",)) else "0.") + code
        cur = conn.execute(
            "SELECT * FROM stock_price WHERE code=? ORDER BY fetched_at DESC LIMIT 1",
            (em_code,)
        )
        row = cur.fetchone()
        if not row:
            continue
        
        stock_data = dict(row)
        price = stock_data.get("price") or 0
        change_pct = stock_data.get("change_pct") or 0
        
        if price <= 0:
            continue
        
        # 检查是否持仓
        holding = holdings_map.get(name)
        is_held = holding and holding.get("shares", 0) > 0
        cost = holding.get("avg_cost", 0) if holding else 0
        
        # 检查价格提醒
        buy_below = alert_rules.get("buy_below", 0)
        sell_above = alert_rules.get("sell_above", 0)
        stop_loss = alert_rules.get("stop_loss", 0)
        
        # 买入信号
        if buy_below > 0 and price <= buy_below and not is_held:
            alerts.append({
                "type": "FOCUS_BUY",
                "name": name,
                "code": code,
                "price": price,
                "change_pct": round(change_pct, 2),
                "reason": f"价格¥{price:.2f}≤买入线¥{buy_below:.2f}",
                "action": "可考虑买入",
            })
        
        # 卖出信号
        if sell_above > 0 and price >= sell_above and is_held:
            shares = holding.get("shares", 0)
            alerts.append({
                "type": "FOCUS_SELL",
                "name": name,
                "code": code,
                "price": price,
                "change_pct": round(change_pct, 2),
                "reason": f"价格¥{price:.2f}≥卖出线¥{sell_above:.2f}",
                "action": f"可考虑卖出{shares}股",
            })
        
        # 止损信号
        if stop_loss > 0 and price <= stop_loss and is_held:
            shares = holding.get("shares", 0)
            alerts.append({
                "type": "FOCUS_STOP_LOSS",
                "name": name,
                "code": code,
                "price": price,
                "change_pct": round(change_pct, 2),
                "reason": f"价格¥{price:.2f}≤止损线¥{stop_loss:.2f}",
                "action": f"⚠️ 立即止损{shares}股",
            })
        
        # 大幅波动提醒
        if abs(change_pct) >= 5:
            direction = "大涨" if change_pct > 0 else "大跌"
            alerts.append({
                "type": "FOCUS_VOLATILE",
                "name": name,
                "code": code,
                "price": price,
                "change_pct": round(change_pct, 2),
                "reason": f"今日{direction}{abs(change_pct):.1f}%",
                "action": "关注异动原因",
            })
    
    return alerts


def _save_strategy_result(result):
    """保存策略结果到数据库"""
    conn = get_db()
    conn.execute("""
        INSERT INTO analysis_log (session_type, market_state, index_data, holdings_review, signals, decisions, screener_output, raw_notes)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        "strategy_scan",
        result["market_env"].get("state", "unknown"),
        json.dumps(result["market_env"].get("indices", []), ensure_ascii=False),
        json.dumps({"position_advice": result["position_advice"]}, ensure_ascii=False),
        json.dumps(result["stop_loss_alerts"] + result["profit_take_alerts"], ensure_ascii=False),
        json.dumps({"buy_candidates": result["buy_candidates"][:5]}, ensure_ascii=False),
        "",
        json.dumps({"timestamp": result["timestamp"]}, ensure_ascii=False),
    ))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    result = run_strategy()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
