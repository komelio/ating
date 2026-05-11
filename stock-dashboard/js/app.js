/* === 小智盯盘 V3.1 - Frontend App === */

// Configuration
const CONFIG = {
  dataBase: 'data',
  refreshInterval: 60000, // 60 seconds
  endpoints: {
    market: 'data/market.json',
    watchlist: 'data/watchlist.json',
    positions: 'data/positions.json',
    news: 'data/news.json',
    analysisIndex: 'data/analysis/index.json',
    analysis: (date) => `data/analysis/${date}.json`
  }
};

// State
let currentTab = 'market';
let currentFilter = 'all';
let refreshTimer = null;
let countdownTimer = null;
let secondsLeft = 60;

// === Initialization ===
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initFilters();
  initAnalysisDateSelector();
  loadAllData();
  startAutoRefresh();
});

// === Tab Navigation ===
function initTabs() {
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTab = btn.dataset.tab;
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      document.getElementById(`tab-${currentTab}`).classList.add('active');
    });
  });
}

// === Watchlist Filters ===
function initFilters() {
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      loadWatchlist();
    });
  });
}

// === Analysis Date Selector ===
async function initAnalysisDateSelector() {
  try {
    const resp = await fetch(CONFIG.endpoints.analysisIndex);
    if (!resp.ok) return;
    const dates = await resp.json();
    const select = document.getElementById('analysisDateSelect');
    select.innerHTML = '<option value="">-- 选择日期 --</option>';
    dates.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d;
      opt.textContent = d;
      select.appendChild(opt);
    });
    select.addEventListener('change', () => {
      if (select.value) loadAnalysis(select.value);
    });
  } catch (e) {
    console.warn('Failed to load analysis index:', e);
  }
}

// === Data Loading ===
async function loadAllData() {
  await Promise.all([
    loadMarket(),
    loadWatchlist(),
    loadPositions(),
    loadNews()
  ]);
}

async function loadMarket() {
  try {
    const resp = await fetch(CONFIG.endpoints.market);
    if (!resp.ok) throw new Error('Failed');
    const data = await resp.json();
    renderMarketTicker(data);
    renderIndices(data);
    renderSectors(data);
    renderStateMachine(data);
    updateTimestamp(data.update_time);
  } catch (e) {
    console.warn('Market data load failed:', e);
    document.getElementById('indexList').innerHTML = '<p class="placeholder">数据加载失败</p>';
  }
}

async function loadWatchlist() {
  try {
    const resp = await fetch(CONFIG.endpoints.watchlist);
    if (!resp.ok) throw new Error('Failed');
    const data = await resp.json();
    renderWatchlist(data);
  } catch (e) {
    console.warn('Watchlist load failed:', e);
    document.getElementById('watchlistBody').innerHTML = '<tr><td colspan="10" class="placeholder">数据加载失败</td></tr>';
  }
}

async function loadPositions() {
  try {
    const resp = await fetch(CONFIG.endpoints.positions);
    if (!resp.ok) throw new Error('Failed');
    const data = await resp.json();
    renderSummaryCards(data);
    renderPositionsTable(data);
    renderRedlines(data);
    renderTrades(data);
  } catch (e) {
    console.warn('Positions load failed:', e);
  }
}

async function loadNews() {
  try {
    const resp = await fetch(CONFIG.endpoints.news);
    if (!resp.ok) throw new Error('Failed');
    const data = await resp.json();
    renderNews(data);
  } catch (e) {
    console.warn('News load failed:', e);
    document.getElementById('newsList').innerHTML = '<p class="placeholder">资讯加载失败</p>';
  }
}

async function loadAnalysis(date) {
  try {
    const resp = await fetch(CONFIG.endpoints.analysis(date));
    if (!resp.ok) throw new Error('Failed');
    const data = await resp.json();
    renderAnalysis(data);
  } catch (e) {
    document.getElementById('analysisContent').innerHTML = '<p class="placeholder">该日期暂无分析记录</p>';
  }
}

// === Render Functions ===

function renderMarketTicker(data) {
  const ticker = document.getElementById('marketTicker');
  if (!data.indices || data.indices.length === 0) {
    ticker.innerHTML = '<span class="ticker-loading">暂无数据</span>';
    return;
  }
  ticker.innerHTML = data.indices.map(i => {
    const cls = i.change_pct >= 0 ? 'up' : 'down';
    const sign = i.change_pct >= 0 ? '+' : '';
    return `<span class="ticker-item">
      <span class="ticker-name">${i.name}</span>
      <span class="ticker-price">${fmtPrice(i.price)}</span>
      <span class="ticker-change ${cls}">${sign}${i.change_pct.toFixed(2)}%</span>
    </span>`;
  }).join('');
}

function renderIndices(data) {
  const el = document.getElementById('indexList');
  if (!data.indices || data.indices.length === 0) {
    el.innerHTML = '<p class="placeholder">暂无数据</p>';
    return;
  }
  el.innerHTML = data.indices.map(i => {
    const cls = i.change_pct >= 0 ? 'up' : 'down';
    const sign = i.change_pct >= 0 ? '+' : '';
    return `<div class="index-row">
      <div class="index-info">
        <span class="index-name">${i.name}</span>
        <span class="index-code">${i.code}</span>
      </div>
      <div class="index-price-block">
        <span class="index-price">${fmtPrice(i.price)}</span>
        <span class="index-change ${cls}">
          <span>${sign}${fmtPrice(i.change)}</span>
          <span>${sign}${i.change_pct.toFixed(2)}%</span>
        </span>
      </div>
    </div>`;
  }).join('');
}

function renderSectors(data) {
  const el = document.getElementById('sectorGrid');
  if (!data.sectors || data.sectors.length === 0) {
    el.innerHTML = '<p class="placeholder">暂无板块数据</p>';
    return;
  }
  el.innerHTML = data.sectors.map(s => {
    const cls = s.change_pct >= 0 ? 'up' : 'down';
    const sign = s.change_pct >= 0 ? '+' : '';
    return `<div class="sector-item">
      <div class="sector-name">${s.name}</div>
      <div class="sector-pct ${cls}">${sign}${s.change_pct.toFixed(2)}%</div>
    </div>`;
  }).join('');
}

function renderStateMachine(data) {
  const el = document.getElementById('stateMachine');
  if (!data.state) {
    el.innerHTML = '<p class="placeholder">暂无状态数据</p>';
    return;
  }
  const state = data.state;
  const stateClassMap = {
    'RiskOn': 'state-risk-on',
    'Neutral': 'state-neutral',
    'RiskOff': 'state-risk-off',
    'Panic': 'state-panic'
  };
  const stateClass = stateClassMap[state.mode] || 'state-neutral';
  const emojiMap = {
    'RiskOn': '🟢', 'Neutral': '🟡', 'RiskOff': '🔴', 'Panic': '🚨'
  };
  
  el.innerHTML = `
    <div class="state-badge ${stateClass}">${emojiMap[state.mode] || ''} ${state.mode}</div>
    <div class="state-details">
      <div>成交额: <strong>${state.volume || '--'}</strong></div>
      <div>涨跌比: <strong>${state.up_down_ratio || '--'}</strong></div>
      <div>北向资金: <strong>${state.north_flow || '--'}</strong></div>
      <div>判定理由: ${state.reason || '--'}</div>
    </div>
  `;
}

function renderWatchlist(data) {
  const tbody = document.getElementById('watchlistBody');
  let stocks = data.stocks || [];
  if (currentFilter !== 'all') {
    stocks = stocks.filter(s => s.type === currentFilter);
  }
  if (stocks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="placeholder">暂无自选股</td></tr>';
    return;
  }
  tbody.innerHTML = stocks.map(s => {
    const pctCls = s.change_pct >= 0 ? 'up' : 'down';
    const sign = s.change_pct >= 0 ? '+' : '';
    const typeTag = s.type === 'cashcow' ? '<span class="tag tag-cashcow">现金牛</span>' : '<span class="tag tag-growth">成长股</span>';
    return `<tr>
      <td>${s.code}</td>
      <td class="name-cell">${s.name}</td>
      <td>${fmtPrice(s.price)}</td>
      <td class="${pctCls}">${sign}${s.change_pct.toFixed(2)}%</td>
      <td>${s.pe != null ? s.pe.toFixed(1) : '--'}</td>
      <td>${s.pb != null ? s.pb.toFixed(2) : '--'}</td>
      <td>${s.roe != null ? (s.roe*100).toFixed(1)+'%' : '--'}</td>
      <td>${s.dividend_yield != null ? (s.dividend_yield*100).toFixed(2)+'%' : '--'}</td>
      <td>${typeTag}</td>
      <td>${s.status || '--'}</td>
    </tr>`;
  }).join('');
}

function renderSummaryCards(data) {
  const el = document.getElementById('summaryCards');
  const s = data.summary || {};
  const pnlCls = (s.total_pnl || 0) >= 0 ? 'up' : 'down';
  const pnlSign = (s.total_pnl || 0) >= 0 ? '+' : '';
  
  el.innerHTML = `
    <div class="summary-card">
      <div class="summary-label">总资产</div>
      <div class="summary-value">¥${fmtMoney(s.total_assets)}</div>
      <div class="summary-sub">累计注入 ¥${fmtMoney(s.total_injected || 0)}</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">现金</div>
      <div class="summary-value">¥${fmtMoney(s.cash)}</div>
      <div class="summary-sub">占比 ${s.cash_pct != null ? s.cash_pct.toFixed(1) : '--'}%</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">持仓市值</div>
      <div class="summary-value">¥${fmtMoney(s.market_value)}</div>
      <div class="summary-sub">${s.holding_count || 0} 只标的</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">总浮盈</div>
      <div class="summary-value ${pnlCls}">${pnlSign}¥${fmtMoney(Math.abs(s.total_pnl || 0))}</div>
      <div class="summary-sub">${pnlSign}${(s.total_pnl_pct || 0).toFixed(2)}%</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">历史峰值</div>
      <div class="summary-value">¥${fmtMoney(s.peak_assets || s.total_assets)}</div>
      <div class="summary-sub">回撤 ${(s.drawdown_pct || 0).toFixed(2)}%</div>
    </div>
  `;
}

function renderPositionsTable(data) {
  const tbody = document.getElementById('positionsBody');
  const holdings = data.holdings || [];
  if (holdings.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="placeholder">暂无持仓</td></tr>';
    return;
  }
  tbody.innerHTML = holdings.map(h => {
    const pnlCls = (h.pnl || 0) >= 0 ? 'up' : 'down';
    const sign = (h.pnl || 0) >= 0 ? '+' : '';
    const typeTag = h.type === 'cashcow' ? '<span class="tag tag-cashcow">现金牛</span>' : '<span class="tag tag-growth">成长股</span>';
    return `<tr>
      <td>${h.code}</td>
      <td class="name-cell">${h.name}</td>
      <td>${h.shares}</td>
      <td>${fmtPrice(h.avg_cost)}</td>
      <td>¥${fmtMoney(h.cost)}</td>
      <td>${fmtPrice(h.current_price)}</td>
      <td>¥${fmtMoney(h.market_value)}</td>
      <td class="${pnlCls}">${sign}¥${fmtMoney(Math.abs(h.pnl || 0))}</td>
      <td class="${pnlCls}">${sign}${(h.pnl_pct || 0).toFixed(2)}%</td>
      <td>${typeTag}</td>
    </tr>`;
  }).join('');
}

function renderRedlines(data) {
  const el = document.getElementById('redlineGrid');
  const rl = data.redlines || [];
  if (rl.length === 0) {
    el.innerHTML = '<p class="placeholder">红线数据暂无</p>';
    return;
  }
  el.innerHTML = rl.map(r => {
    let statusCls = '';
    if (r.status === 'warn') statusCls = 'warn';
    if (r.status === 'danger') statusCls = 'danger';
    const icons = { ok: '✅', warn: '⚠️', danger: '🔴' };
    return `<div class="redline-item ${statusCls}">
      <span class="redline-label">${r.name}</span>
      <span class="redline-value">${icons[r.status] || ''} ${r.value} / ${r.limit}</span>
    </div>`;
  }).join('');
}

function renderTrades(data) {
  const tbody = document.getElementById('tradesBody');
  const trades = data.trades || [];
  if (trades.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="placeholder">暂无交易记录</td></tr>';
    return;
  }
  tbody.innerHTML = trades.map(t => {
    const actionTag = t.action === 'BUY' ? '<span class="tag tag-buy">买入</span>' : '<span class="tag tag-sell">卖出</span>';
    return `<tr>
      <td>${t.date}</td>
      <td>${actionTag}</td>
      <td>${t.code}</td>
      <td class="name-cell">${t.name}</td>
      <td>${t.shares}</td>
      <td>${fmtPrice(t.price)}</td>
      <td>¥${fmtMoney(t.amount)}</td>
    </tr>`;
  }).join('');
}

function renderNews(data) {
  const el = document.getElementById('newsList');
  const items = data.items || [];
  if (items.length === 0) {
    el.innerHTML = '<p class="placeholder">暂无资讯</p>';
    return;
  }
  el.innerHTML = items.map(n => `
    <div class="news-item">
      <div class="news-time">${n.time || ''}</div>
      <div class="news-title"><a href="${n.url || '#'}" target="_blank">${n.title}</a></div>
      <div class="news-source">${n.source || ''}</div>
    </div>
  `).join('');
}

function renderAnalysis(data) {
  const el = document.getElementById('analysisContent');
  
  let html = '';
  
  // Market State
  if (data.market_state) {
    html += `<div class="analysis-block">
      <h3>📈 市场状态机: ${data.market_state.mode || '--'}</h3>
      <div class="info-row"><span>成交额</span><strong>${data.market_state.volume || '--'}</strong></div>
      <div class="info-row"><span>涨跌比</span><strong>${data.market_state.up_down_ratio || '--'}</strong></div>
      <div class="info-row"><span>判定理由</span><strong>${data.market_state.reason || '--'}</strong></div>
    </div>`;
  }
  
  // PELT Warnings
  if (data.pelt_warnings && data.pelt_warnings.length > 0) {
    html += `<div class="analysis-block">
      <h3>⚠️ PELT预警</h3>
      ${data.pelt_warnings.map(w => 
        `<div class="info-row"><span>${w.stock || w.code}</span><strong>${w.warning}</strong></div>`
      ).join('')}
    </div>`;
  }
  
  // Decisions
  if (data.decisions && data.decisions.length > 0) {
    html += `<div class="analysis-block">
      <h3>🎯 当日决策</h3>
      ${data.decisions.map(d => 
        `<div class="info-row"><span>${d.action || d.type}</span><strong>${d.detail}</strong></div>`
      ).join('')}
    </div>`;
  }
  
  // Thoughts
  if (data.thoughts) {
    html += `<div class="analysis-block">
      <h3>💭 分析思路</h3>
      <div class="analysis-thoughts">${data.thoughts}</div>
    </div>`;
  }
  
  el.innerHTML = html || '<p class="placeholder">暂无分析数据</p>';
}

// === Auto Refresh ===
function startAutoRefresh() {
  refreshTimer = setInterval(loadAllData, CONFIG.refreshInterval);
  countdownTimer = setInterval(updateCountdown, 1000);
}

function updateCountdown() {
  secondsLeft--;
  if (secondsLeft <= 0) secondsLeft = CONFIG.refreshInterval / 1000;
  document.getElementById('refreshInfo').textContent = `刷新 ${secondsLeft}s`;
}

function updateTimestamp(ts) {
  document.getElementById('updateTime').textContent = `📡 ${ts || '--'}`;
  document.getElementById('dataTimestamp').textContent = `数据更新: ${ts || '--'}`;
}

// === Helpers ===
function fmtPrice(v) {
  if (v == null || isNaN(v)) return '--';
  if (Number.isInteger(v)) return v.toLocaleString();
  return v.toFixed(2);
}

function fmtMoney(v) {
  if (v == null || isNaN(v)) return '--';
  if (Math.abs(v) >= 10000) {
    return (v / 10000).toFixed(2) + '万';
  }
  return v.toFixed(0);
}