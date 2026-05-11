# 🛠️ 小智盯盘 V3.1

A股模拟盘实时盯盘面板 | V3.1 Simulated Portfolio Dashboard

## 架构

```
stock-dashboard/
├── index.html          # 主页面 (5个Tab)
├── css/style.css       # 交易终端风格
├── js/app.js           # 前端逻辑, JSON驱动
├── data/               # JSON数据文件
│   ├── market.json     # 大盘指数 + 板块 + 状态机
│   ├── watchlist.json  # 自选股监控
│   ├── positions.json  # 持仓 + 红线 + 交易记录
│   ├── news.json       # 市场资讯
│   └── analysis/       # 历史分析记录
├── fetcher/            # Python数据引擎
│   ├── fetch_data.py   # 数据抓取 + SQLite + JSON导出
│   ├── schema.sql      # 数据库表结构
│   ├── refresh.sh      # 自动刷新 & 推送脚本
│   └── requirements.txt
└── .github/workflows/  # CI/CD (备选)
```

## 数据流

```
东方财富API → fetch_data.py → SQLite → JSON → GitHub Pages
                    ↑
              模拟盘 state.json
```

## 访问

**在线面板:** [https://komelio.github.io/ating/stock-dashboard/](https://komelio.github.io/ating/stock-dashboard/)

## 本地运行

```bash
# 安装依赖
pip install -r fetcher/requirements.txt

# 刷新市场数据
python3 fetcher/fetch_data.py refresh

# 运行分析记录
python3 fetcher/fetch_data.py analysis

# 一键刷新+推送
bash fetcher/refresh.sh
```

## 定时任务

添加到 crontab (交易日 9:30-15:30 每5分钟):
```
*/5 9-15 * * 1-5 /path/to/stock-dashboard/fetcher/refresh.sh
```

或通过 OpenClaw 心跳任务调度。

## Tab说明

| Tab | 内容 | 数据源 |
|-----|------|--------|
| 📈 大盘 | 主要指数、板块热力、状态机 | 东方财富API |
| ⭐ 自选 | 自选股行情、估值、筛选 | 东方财富 + watchlist.json |
| 💼 持仓 | 资产总览、持仓明细、红线监控 | 模拟盘 state.json |
| 📊 数据 | 历史盯盘分析记录 | analysis/ |
| 📰 资讯 | 市场要闻 | 缓存 + 手动更新 |