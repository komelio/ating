# -*- coding: utf-8 -*-
"""V3.1 Dashboard — 盯盘分析记录模块。
每次执行盯盘/扫描/定投决策时调用，将分析过程写入 SQLite，供复盘。
"""
import os, sys, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from db import get_db, init_db, export_all_json


def run_morning_watch():
    """早盘盯盘分析（9:40 调用）"""
    log = _base_analysis("morning_watch")
    return _save(log)


def run_afternoon_watch():
    """午盘盯盘分析（14:40 调用）"""
    log = _base_analysis("afternoon_watch")
    return _save(log)


def run_weekly_scan():
    """每周扫盘分析（周六调用）"""
    log = _base_analysis("weekly_scan")
    log["screener_output"] = _run_screener()
    return _save(log)


def run_dca_decision():
    """每月定投决策（15日调用）"""
    log = _base_analysis("dca_decision")
    log["decisions"] = _dca_logic(log)
    return _save(log)


def run_monthly_review():
    """月度复盘（每月1日调用，也可手动触发）"""
    log = _base_analysis("monthly_review")

    # 调用 portfolio.py review 获取完整月度报告
    import subprocess
    rev_path = os.path.expanduser("~/.hermes/scripts/portfolio.py")
    try:
        r = subprocess.run(["python3", rev_path, "review"], capture_output=True, text=True, timeout=30)
        review_text = r.stdout.strip() or r.stderr.strip()
    except Exception as e:
        review_text = f"复盘脚本执行失败: {e}"

    # 复盘报告放进 screener_output 字段（前端会渲染 <pre> 块）
    log["screener_output"] = review_text
    log["decisions"] = json.dumps({
        "reasoning": "月度合规检查 + 利润锁定规则校验 + 持仓健康度评估。详见复盘报告。"
    }, ensure_ascii=False)
    return _save(log)


def _base_analysis(session_type):
    """抽取当前状态快照作为分析基础。"""
    conn = get_db()

    # 大盘状态
    cur = conn.execute("""
        SELECT name, price, change_pct FROM market_index
        WHERE fetched_at > datetime('now','-1 day')
        ORDER BY fetched_at DESC LIMIT 3
    """)
    idx = [dict(r) for r in cur.fetchall()]
    ss_chg = sum((i.get("change_pct") or 0) for i in idx) if idx else 0
    if ss_chg > 1:  state = "bull"
    elif ss_chg < -1: state = "bear"
    else: state = "shock"

    # 持仓
    try:
        with open(os.path.expanduser("~/.hermes/portfolio/sim-portfolio.json")) as f:
            port = json.load(f)
    except Exception:
        port = {}
    raw_holdings = port.get("holdings", {})
    # holdings may be dict (keyed by name) or list; normalize to list of dicts
    if isinstance(raw_holdings, dict):
        holdings = [{"name": k, **v} for k, v in raw_holdings.items()]
    elif isinstance(raw_holdings, list):
        holdings = raw_holdings
    else:
        holdings = []
    cash = float(port.get("current_cash", port.get("cash", 0)))

    # 先获取实时价格
    stocks = _latest_stocks(conn)
    price_map = {s["code"]: s for s in stocks}

    # 计算总市值
    total_mv = 0
    for h in holdings:
        code = _find_code(h["name"])
        s = price_map.get(code, {})
        cur_p = s.get("price") or 0
        total_mv += cur_p * (h.get("shares") or 0)
    total = cash + total_mv
    profit = total - 100000

    # 个股信号
    signals = []
    for h in holdings:
        code = _find_code(h["name"])
        s = price_map.get(code, {})
        cur_price = s.get("price")
        chg_pct = s.get("change_pct") or 0
        cost = h.get("cost_price") or h.get("avg_cost") or 0
        if cur_price and cost:
            pnl_pct = (cur_price - cost) / cost * 100
            if pnl_pct <= -15:
                signals.append(f"🔴 {h['name']} 回撤{abs(pnl_pct):.1f}%，触发15%硬止损")
            elif pnl_pct <= -8:
                signals.append(f"🟡 {h['name']} 回撤{abs(pnl_pct):.1f}%，接近警戒线")
            elif chg_pct <= -5:
                signals.append(f"⚠️ {h['name']} 单日跌{abs(chg_pct):.1f}%")
            elif chg_pct >= 5:
                signals.append(f"📈 {h['name']} 单日涨{chg_pct:.1f}%")

    conn.close()

    return {
        "session_type": session_type,
        "market_state": state,
        "index_data": json.dumps(idx, ensure_ascii=False),
        "holdings_review": json.dumps({
            "total_asset": round(total, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit/100000*100, 2),
            "positions": len(holdings),
        }, ensure_ascii=False),
        "signals": json.dumps(signals, ensure_ascii=False),
        "decisions": "",
        "screener_output": "",
        "raw_notes": "",
    }


def _dca_logic(log):
    """定投决策逻辑。"""
    state = log["market_state"]
    idx_data = json.loads(log["index_data"])
    avg_chg = sum(i.get("change_pct", 0) for i in idx_data) / max(len(idx_data), 1)

    if state == "bear":
        ratio = 1.5  # 跌市加倍
        msg = f"🐻 熊市信号，定投系数 1.5x。近月均值变化 {avg_chg:.1f}%。建议：优先补仓现金牛、暂缓成长股、不开拓荒。"
    elif state == "bull":
        ratio = 0.8
        msg = f"🐂 牛市信号，定投系数 0.8x。建议：适度减持高估值标的，保持现金≥15%。"
    else:
        ratio = 1.0
        msg = f"📊 震荡市，标准定投。建议：按目标配置比例再平衡，现金牛优先。"

    return json.dumps({"ratio": ratio, "reasoning": msg}, ensure_ascii=False)


def _run_screener():
    """调用筛股脚本获取输出。"""
    path = os.path.expanduser("~/.hermes/scripts/screener.py")
    if not os.path.exists(path):
        return "screener.py 不存在"
    import subprocess
    try:
        r = subprocess.run(["python3", path], capture_output=True, text=True, timeout=60)
        return r.stdout[:3000] or r.stderr[:1000]
    except Exception as e:
        return str(e)


def _latest_stocks(conn):
    cur = conn.execute("""
        SELECT sp.* FROM stock_price sp
        INNER JOIN (
            SELECT code, MAX(fetched_at) mx FROM stock_price
            WHERE fetched_at > datetime('now','-1 day')
            GROUP BY code
        ) latest ON sp.code=latest.code AND sp.fetched_at=latest.mx
    """)
    return [dict(r) for r in cur.fetchall()]


def _find_code(name):
    mapping = {
        "五粮液":"0.000858","中国神华":"1.601088","粤高速A":"0.000429",
        "中国移动":"1.600941","工商银行":"1.601398","拓普集团":"1.601689",
        "三花智控":"0.002050","贵州茅台":"1.600519","长江电力":"1.600900",
        "片仔癀":"1.600436","寒武纪":"1.688256","中际旭创":"0.300308",
        "海光信息":"1.688041","国电南瑞":"1.600406","许继电气":"0.000400",
        "航天晨光":"1.600501","江顺科技":"0.003031","比亚迪":"0.002594",
        "宁德时代":"0.300750","中国平安":"1.601318",
        "招商银行":"1.600036","美的集团":"0.000333",
        "恒瑞医药":"1.600276",
    }
    return mapping.get(name, "")


def _save(log):
    conn = get_db()
    conn.execute("""
        INSERT INTO analysis_log (session_type,market_state,index_data,holdings_review,signals,decisions,screener_output,raw_notes)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        log["session_type"], log["market_state"], log["index_data"],
        log["holdings_review"], log["signals"], log.get("decisions", ""),
        log.get("screener_output", ""), log.get("raw_notes", ""),
    ))
    conn.commit()
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    export_all_json()
    print(f"📝 分析记录 #{rid} 已保存 [{log['session_type']}] 状态:{log['market_state']}")
    return rid


if __name__ == "__main__":
    init_db()
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["morning","afternoon","weekly","dca","review"], default="morning")
    args = p.parse_args()
    {
        "morning": run_morning_watch,
        "afternoon": run_afternoon_watch,
        "weekly": run_weekly_scan,
        "dca": run_dca_decision,
        "review": run_monthly_review,
    }[args.mode]()