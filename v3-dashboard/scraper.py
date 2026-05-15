# -*- coding: utf-8 -*-
"""V3.1 Dashboard — 数据采集器。新浪 API → SQLite（增量写入）。"""
import os, sys, json, time, urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from db import get_db, init_db, export_all_json

# ── 自选股列表 (code, name) ──
# 代码自动识别市场：6开头=上海(sh), 0/3开头=深圳(sz)
WATCHLIST = [
    # ── 现金牛 Core Income ──
    ("000858", "五粮液"),   ("601088", "中国神华"), ("000429", "粤高速A"),
    ("600941", "中国移动"), ("601398", "工商银行"), ("600519", "贵州茅台"),
    ("600900", "长江电力"), ("600436", "片仔癀"),
    # ── 成长龙头 Cycle Growth ──
    ("601689", "拓普集团"), ("002050", "三花智控"),
    ("688256", "寒武纪"),   ("688041", "海光信息"),
    ("600406", "国电南瑞"), ("000400", "许继电气"),
    ("600391", "航天晨光"), ("003031", "江顺科技"),
    # ── 2026-05-15 新增：AI芯片上游 + 能源算力 ──
    ("002371", "北方华创"), # 半导体设备平台龙头
    ("688012", "中微公司"), # 刻蚀设备龙头
    ("601985", "中国核电"), # 核电基荷/AI数据中心锁长协
    ("600584", "长电科技"), # 先进封装 CoWoS
    ("002837", "英维克"),   # 液冷散热
    ("003816", "中国广核"), # 核电补充
    # ── 蓝筹观察池 ──
    ("002594", "比亚迪"),   ("300750", "宁德时代"),
    ("601318", "中国平安"), ("600036", "招商银行"),
    ("000333", "美的集团"), ("600276", "恒瑞医药"),
    # ── 降级观察（已透支，仅追踪不主动买入）──
    # ("300308", "中际旭创"),  # 光模块，2026-05研判：预期透支2年
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

    # 补充 PE 数据（东方财富）
    _enrich_pe(conn, count)


def _enrich_pe(conn, stock_count):
    """用东方财富 API 补充 PE 数据，失败时用内嵌常量兜底。"""
    if stock_count == 0:
        return
    print("📊 PE 补充...", end=" ")
    
    # Fallback PE values (API不可用时用)
    PE_FALLBACK = {
        "000858": 22.5, "601088": 10.2, "000429": 15.8, "600941": 14.1,
        "601398": 6.2,  "601689": 35.6, "002050": 42.1, "600519": 32.8,
        "600900": 20.5, "600436": 55.2, "688256": -1,   "300308": 48.5,
        "688041": 120.5,"600406": 28.3, "000400": 22.8, "600391": 55.0,
        "003031": 38.5, "002594": 32.1, "300750": 25.8, "601318": 9.5,
        "600036": 7.2,  "000333": 16.5, "600276": 55.0,
    }
    
    api_ok = False
    updated = 0
    for code, name in WATCHLIST:
        pe = PE_FALLBACK.get(code)
        try:
            mkt = "1" if code.startswith(("6", "68")) else "0"
            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={mkt}.{code}&fields=f162"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"
            })
            with urllib.request.urlopen(req, timeout=4) as resp:
                pe_raw = json.loads(resp.read().decode("utf-8")).get("data", {}).get("f162")
            if pe_raw is not None:
                pe = pe_raw / 100 if pe_raw != "-" else PE_FALLBACK.get(code, 0)
                api_ok = True
        except:
            pass
        if pe is not None:
            em_code = f"{'1' if code.startswith(('6','68')) else '0'}.{code}"
            conn.execute("UPDATE stock_price SET pe=? WHERE code=? AND fetched_at > datetime('now','-1 day')",
                         (pe, em_code))
            updated += 1
        time.sleep(0.05)
    conn.commit()
    src = "API" if api_ok else "常量"
    print(f"{updated}只 ✓ ({src})")


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


def _ensure_seed_data(conn):
    """若资讯/分析表为空，注入种子数据防止 tab 空白。"""
    # News
    cnt = conn.execute("SELECT COUNT(*) FROM ai_news").fetchone()[0]
    if cnt == 0:
        default_news = [
            ("梁文锋出资200亿！DeepSeek首轮融资500亿，V4.1定档6月","量子位","https://www.qbitai.com","国内AI","2026-05-11"),
            ("Redis之父给DeepSeek V4单独造了推理引擎","量子位","https://www.qbitai.com","开源","2026-05-10"),
            ("百度文心5.1：搜索登顶国内，预训练成本仅业界6%","量子位","https://www.qbitai.com","国内AI","2026-05-10"),
            ("Nvidia今年已承诺400亿美元AI股权投资","TechCrunch","https://techcrunch.com","硬件","2026-05-10"),
            ("GPT-5推理能力塞进语音模型，OpenAI翻译成本砍穿地板价","量子位","https://www.qbitai.com","模型","2026-05-09"),
            ("Anthropic出手！AI内心独白曝光——Claude可解释性突破","量子位","https://www.qbitai.com","安全","2026-05-09"),
            ("所有实验室都怕字节，所有人都在夸DeepSeek","量子位","https://www.qbitai.com","国内AI","2026-05-09"),
            ("马斯克vs OpenAI庭审：前CTO称无法信任Altman","The Verge","https://www.theverge.com","AI行业","2026-05-11"),
            ("阶跃星辰语音模型位列评测榜中国第一","量子位","https://www.qbitai.com","国内AI","2026-05-08"),
            ("微软内部邮件：曾担心OpenAI跑去亚马逊并诋毁Azure","The Verge","https://www.theverge.com","AI行业","2026-05-08"),
        ]
        conn.executemany("INSERT INTO ai_news(title,source,url,category,published_at) VALUES(?,?,?,?,?)", default_news)
        conn.commit()
        print(f"📰 种子资讯: {len(default_news)}条 ✓")

    # Analysis — removed, now handled by analysis.py


def fetch_news(conn=None):
    """从新浪财经抓取实时快讯，写入 ai_news 表（去重，保留最新50条）。"""
    import urllib.request, re
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True

    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=20&page=1"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://finance.sina.com.cn/"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        items = data.get("result", {}).get("data", [])

        existing = set(r[0] for r in conn.execute("SELECT title FROM ai_news").fetchall())
        added = 0
        today = datetime.now().strftime("%Y-%m-%d")

        for item in items[:20]:
            title = (item.get("title") or "").strip()
            if not title or title in existing:
                continue
            source = item.get("media_name") or item.get("source") or "新浪财经"
            url_link = item.get("url") or ""
            category = _classify_news(title)
            ctime = item.get("ctime")
            if ctime:
                try:
                    pub_date = datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d")
                except:
                    pub_date = today
            else:
                pub_date = today

            conn.execute(
                "INSERT INTO ai_news(title,source,url,category,published_at) VALUES(?,?,?,?,?)",
                (title, source, url_link, category, pub_date)
            )
            existing.add(title)
            added += 1

        conn.commit()

        # 保留最新 50 条
        conn.execute("DELETE FROM ai_news WHERE id NOT IN (SELECT id FROM ai_news ORDER BY fetched_at DESC LIMIT 50)")

        if added:
            print(f"📰 抓取资讯: +{added}条 (总计{len(existing)}条)")
        else:
            print(f"📰 资讯已最新 ({len(existing)}条)")

    except Exception as e:
        print(f"📰 资讯抓取失败: {e}")
    finally:
        if close_conn:
            conn.close()


def _classify_news(title):
    """根据标题关键词分类。"""
    if any(kw in title for kw in ["AI","大模型","GPT","DeepSeek","Claude","OpenAI","文心","通义","盘古","模型"]):
        return "AI模型"
    if any(kw in title for kw in ["芯片","GPU","Nvidia","AMD","算力","华为","昇腾","服务器"]):
        return "硬件算力"
    if any(kw in title for kw in ["A股","上证","深证","创业板","涨停","跌停","牛市","熊市","行情","大盘"]):
        return "市场行情"
    if any(kw in title for kw in ["政策","央行","证监会","监管","降息","降准","LPR"]):
        return "政策监管"
    if any(kw in title for kw in ["新能源","光伏","锂电","汽车","比亚迪","特斯拉"]):
        return "新能源"
    if any(kw in title for kw in ["机器人","低空","航天","卫星","商业航天"]):
        return "前沿科技"
    if any(kw in title for kw in ["腾讯","阿里","字节","美团","拼多多","京东"]):
        return "互联网"
    if any(kw in title for kw in ["美股","纳斯达克","道琼斯","标普","美联储"]):
        return "海外市场"
    return "财经综合"


def main():
    init_db()
    conn = get_db()
    try:
        collect_market(conn)
        collect_stocks(conn)
        collect_portfolio(conn)
        _ensure_seed_data(conn)
        fetch_news(conn)
        export_all_json()
        print("✅ 采集完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()