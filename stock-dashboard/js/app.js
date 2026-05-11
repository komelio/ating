/* === 小智盯盘 V3.1 - Frontend App === */

const CONFIG = {
  refreshInterval: 60000,
  endpoints: {
    market: 'data/market.json',
    watchlist: 'data/watchlist.json',
    positions: 'data/positions.json',
    review: 'data/review.json',
    news: 'data/news.json',
    analysisIndex: 'data/analysis/index.json',
    analysis: (date) => `data/analysis/${date}.json`
  }
};

let currentTab = 'market';
let currentFilter = 'all';
let refreshTimer = null;
let countdownTimer = null;
let secondsLeft = 60;
let sortBy = 'code';
let sortDir = 'asc';
let cachedWatchlist = [];
let analysisRecords = [];
let analysisPage = 0;
const PAGE_SIZE = 20;

// === Init ===
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initWatchlistFilters();
  initSortableHeaders();
  loadAllData();
  startAutoRefresh();
});

// === Tabs ===
function initTabs() {
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTab = btn.dataset.tab;
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      document.getElementById(`tab-${currentTab}`).classList.add('active');
      if (currentTab === 'data' && analysisRecords.length === 0) loadAnalysisData();
    });
  });
}

// === Watchlist Filters ===
function initWatchlistFilters() {
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      renderWatchlistSorted();
    });
  });
}

// === Sortable ===
function initSortableHeaders() {
  document.querySelectorAll('#watchlistTable .sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      sortDir = (sortBy === col && sortDir === 'asc') ? 'desc' : 'asc';
      sortBy = col;
      updateSortIndicators();
      renderWatchlistSorted();
    });
  });
}

function updateSortIndicators() {
  document.querySelectorAll('#watchlistTable .sortable').forEach(th => {
    const icon = th.querySelector('.sort-icon');
    icon.textContent = th.dataset.sort === sortBy ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';
  });
}

function scoreValue(s) {
  const m = {'S':10,'A+':9,'A':8,'A-':7,'B+':6,'B':5,'B-':4,'C+':3,'C':2,'C-':1,'D':0};
  return m[s] != null ? m[s] : 0;
}

// === Data Loading ===
async function loadAllData() {
  await Promise.all([loadMarket(), loadWatchlist(), loadPositions(), loadReview(), loadNews()]);
}

async function loadMarket() {
  try {
    const d = await (await fetch(CONFIG.endpoints.market)).json();
    renderMarketTicker(d); renderIndices(d); renderSectors(d); renderStateMachine(d);
    updateTimestamp(d.update_time);
  } catch (e) { document.getElementById('indexList').innerHTML = '<p class="placeholder">加载失败</p>'; }
}

async function loadWatchlist() {
  try {
    const d = await (await fetch(CONFIG.endpoints.watchlist)).json();
    cachedWatchlist = d.stocks || [];
    updateSortIndicators();
    renderWatchlistSorted();
  } catch (e) {
    document.getElementById('watchlistBody').innerHTML = '<tr><td colspan="9" class="placeholder">加载失败</td></tr>';
  }
}

async function loadPositions() {
  try {
    const d = await (await fetch(CONFIG.endpoints.positions)).json();
    renderSummaryCards(d); renderPositionsTable(d); renderRedlines(d); renderTrades(d);
  } catch (e) {}
}

async function loadReview() {
  try {
    const d = await (await fetch(CONFIG.endpoints.review)).json();
    renderReview(d);
  } catch (e) { document.getElementById('reviewList').innerHTML = '<p class="placeholder">加载失败</p>'; }
}

async function loadNews() {
  try {
    const d = await (await fetch(CONFIG.endpoints.news)).json();
    document.getElementById('newsList').innerHTML = d.items.map(n => `
      <div class="news-item"><div class="news-time">${n.time||''}</div>
      <div class="news-title"><a href="${n.url||'#'}" target="_blank">${n.title}</a></div>
      <div class="news-source">${n.source||''}</div></div>`).join('');
  } catch (e) { document.getElementById('newsList').innerHTML = '<p class="placeholder">加载失败</p>'; }
}

// === Analysis Data Tab ===
async function loadAnalysisData() {
  try {
    const dates = await (await fetch(CONFIG.endpoints.analysisIndex)).json();
    const records = [];
    for (const date of dates) {
      try { const r = await fetch(CONFIG.endpoints.analysis(date)); if (r.ok) records.push(await r.json()); } catch (e) {}
    }
    analysisRecords = records;
    analysisPage = 0;
  } catch (e) { analysisRecords = []; }
  renderAnalysisPage();
}

function renderAnalysisPage() {
  const total = analysisRecords.length;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const page = analysisRecords.slice(analysisPage * PAGE_SIZE, (analysisPage + 1) * PAGE_SIZE);

  document.getElementById('recordInfo').textContent = `共 ${total} 条记录`;

  const listEl = document.getElementById('analysisList');
  if (!page.length) {
    listEl.innerHTML = '<p class="placeholder">暂无分析记录，收盘后自动生成</p>';
    document.getElementById('analysisPagination').innerHTML = '';
    return;
  }

  listEl.innerHTML = page.map(data => {
    const mode = data.market_state?.mode || '--';
    const sc = {'RiskOn':'state-risk-on','Neutral':'state-neutral','RiskOff':'state-risk-off','Panic':'state-panic'};
    const pelt = (data.pelt_warnings||[]).map(w => `<span class="al-tag al-tag-warn">${w.stock||w.code}: ${w.warning}</span>`).join('');
    const decs = (data.decisions||[]).map(d => `<div class="al-decision"><b>${d.action}</b> ${d.detail}</div>`).join('');
    return `<div class="analysis-card">
      <div class="ac-header"><span class="ac-date">📅 ${data.date}</span><span class="ac-time">${data.analysis_time||''}</span><span class="state-badge-sm ${sc[mode]||'state-neutral'}">${mode}</span></div>
      <div class="ac-body">
        <div class="al-block"><div class="al-meta"><span>成交额: <b>${data.market_state?.volume||'--'}</b></span><span>涨跌比: <b>${data.market_state?.up_down_ratio||'--'}</b></span><span>${data.market_state?.reason||''}</span></div></div>
        ${pelt?`<div class="al-block"><h4>⚠️ PELT预警</h4>${pelt}</div>`:''}
        ${decs?`<div class="al-block"><h4>🎯 决策</h4>${decs}</div>`:''}
        ${data.thoughts?`<div class="al-block"><h4>💭 思路</h4><div class="al-thoughts">${data.thoughts}</div></div>`:''}
      </div></div>`;
  }).join('');

  const pagEl = document.getElementById('analysisPagination');
  if (totalPages <= 1) { pagEl.innerHTML = ''; return; }
  pagEl.innerHTML = `
    <button class="page-btn" ${analysisPage===0?'disabled':''} onclick="analysisPage=0;renderAnalysisPage()">««</button>
    <button class="page-btn" ${analysisPage===0?'disabled':''} onclick="analysisPage--;renderAnalysisPage()">«</button>
    <span class="page-info">${analysisPage+1} / ${totalPages}</span>
    <button class="page-btn" ${analysisPage>=totalPages-1?'disabled':''} onclick="analysisPage++;renderAnalysisPage()">»</button>
    <button class="page-btn" ${analysisPage>=totalPages-1?'disabled':''} onclick="analysisPage=${totalPages-1};renderAnalysisPage()">»»</button>`;
}

// === Render Functions ===

function renderMarketTicker(d) {
  const t = document.getElementById('marketTicker');
  if (!d.indices?.length) { t.innerHTML = '<span class="ticker-loading">暂无</span>'; return; }
  t.innerHTML = d.indices.map(i => `<span class="ticker-item"><span class="ticker-name">${i.name}</span><span class="ticker-price">${fmtP(i.price)}</span><span class="ticker-change ${i.change_pct>=0?'up':'down'}">${i.change_pct>=0?'+':''}${i.change_pct.toFixed(2)}%</span></span>`).join('');
}

function renderIndices(d) {
  const el = document.getElementById('indexList');
  if (!d.indices?.length) { el.innerHTML = '<p class="placeholder">暂无</p>'; return; }
  el.innerHTML = d.indices.map(i => {
    const cls = i.change_pct >= 0 ? 'up' : 'down', s = i.change_pct >= 0 ? '+' : '';
    return `<div class="index-row"><div class="index-info"><span class="index-name">${i.name}</span><span class="index-code">${i.code}</span></div><div class="index-price-block"><span class="index-price">${fmtP(i.price)}</span><span class="index-change ${cls}"><span>${s}${fmtP(i.change)}</span><span>${s}${i.change_pct.toFixed(2)}%</span></span></div></div>`;
  }).join('');
}

function renderSectors(d) {
  const el = document.getElementById('sectorGrid');
  const secs = d.sectors || [];
  if (!secs.length) { el.innerHTML = '<p class="placeholder">板块数据抓取中...</p>'; return; }
  el.innerHTML = secs.map(s => {
    const cls = (s.change_pct||0) >= 0 ? 'up' : 'down', sg = (s.change_pct||0) >= 0 ? '+' : '';
    return `<div class="sector-item"><div class="sector-name">${s.name}</div><div class="sector-pct ${cls}">${sg}${(s.change_pct||0).toFixed(2)}%</div></div>`;
  }).join('');
}

function renderStateMachine(d) {
  const st = d.state || {};
  const cm = {'RiskOn':'state-risk-on','Neutral':'state-neutral','RiskOff':'state-risk-off','Panic':'state-panic'};
  const em = {'RiskOn':'🟢','Neutral':'🟡','RiskOff':'🔴','Panic':'🚨'};
  document.getElementById('stateMachine').innerHTML = `
    <div class="state-badge ${cm[st.mode]||'state-neutral'}">${em[st.mode]||''} ${st.mode||'--'}</div>
    <div class="state-details"><div>成交额: <strong>${st.volume||'--'}</strong></div><div>涨跌比: <strong>${st.up_down_ratio||'--'}</strong></div><div>北向: <strong>${st.north_flow||'--'}</strong></div><div>${st.reason||''}</div></div>`;
}

function renderWatchlistSorted() {
  let stocks = [...cachedWatchlist];
  if (currentFilter !== 'all') stocks = stocks.filter(s => s.type === currentFilter);
  stocks.sort((a, b) => {
    let va, vb;
    if (sortBy === 'score') { va = scoreValue(a.score); vb = scoreValue(b.score); }
    else if (['change_pct','price','pe','dividend_yield'].includes(sortBy)) {
      va = a[sortBy] != null ? a[sortBy] : -Infinity; vb = b[sortBy] != null ? b[sortBy] : -Infinity;
    } else if (sortBy === 'name') { va = a.name||''; vb = b.name||''; }
    else if (sortBy === 'type') { const o = {top10:0,cashcow:1,growth:2}; va = o[a.type]||9; vb = o[b.type]||9; }
    else { va = a[sortBy]||''; vb = b[sortBy]||''; }
    return sortDir === 'asc' ? (va>vb?1:va<vb?-1:0) : (va<vb?1:va>vb?-1:0);
  });
  renderWatchlistTable(stocks);
}

function renderWatchlistTable(stocks) {
  const t = document.getElementById('watchlistBody');
  if (!stocks.length) { t.innerHTML = '<tr><td colspan="9" class="placeholder">无匹配</td></tr>'; return; }
  const sc = {'S':'score-s','A+':'score-a','A':'score-a','A-':'score-a','B+':'score-b','B':'score-b','B-':'score-b','C+':'score-c','C':'score-c','D':'score-d'};
  const tt = {top10:'<span class="tag tag-top10">🏆Top10</span>',cashcow:'<span class="tag tag-cashcow">🐮现金牛</span>',growth:'<span class="tag tag-growth">🚀成长</span>'};
  t.innerHTML = stocks.map(s => {
    const pc = (s.change_pct||0)>=0?'up':'down', sg = (s.change_pct||0)>=0?'+':'';
    const tags = (s.tags||[]).slice(0,2).map(x=>`<span class="tag-mini">${x}</span>`).join('');
    const dy = s.dividend_yield!=null?(s.dividend_yield*100).toFixed(2)+'%':'--';
    const pe = s.pe!=null?(s.pe<0?'亏损':s.pe.toFixed(1)):'--';
    return `<tr title="${s.logic||''}" class="clickable-row" onclick="ChartModule.open('${s.code}')">
      <td>${s.code}</td><td class="name-cell">${s.name}</td><td>${fmtP(s.price)}</td>
      <td class="${pc}">${sg}${(s.change_pct||0).toFixed(2)}%</td>
      <td><span class="score-badge ${sc[s.score]||''}">${s.score||'--'}</span></td>
      <td>${pe}</td><td>${dy}</td><td class="tags-cell">${tags}</td><td>${tt[s.type]||s.type}</td></tr>`;
  }).join('');
}

function renderSummaryCards(d) {
  const s = d.summary || {};
  document.getElementById('summaryCards').innerHTML = `
    <div class="summary-card"><div class="summary-label">总资产</div><div class="summary-value">¥${fmtM(s.total_assets)}</div><div class="summary-sub">注入 ¥${fmtM(s.total_injected||0)}</div></div>
    <div class="summary-card"><div class="summary-label">现金</div><div class="summary-value">¥${fmtM(s.cash)}</div><div class="summary-sub">${s.cash_pct!=null?s.cash_pct.toFixed(1):'--'}%</div></div>
    <div class="summary-card"><div class="summary-label">市值</div><div class="summary-value">¥${fmtM(s.market_value)}</div><div class="summary-sub">${s.holding_count||0} 只</div></div>
    <div class="summary-card"><div class="summary-label">浮盈</div><div class="summary-value ${(s.total_pnl||0)>=0?'up':'down'}">${(s.total_pnl||0)>=0?'+':''}¥${fmtM(Math.abs(s.total_pnl||0))}</div><div class="summary-sub">${(s.total_pnl||0)>=0?'+':''}${(s.total_pnl_pct||0).toFixed(2)}%</div></div>
    <div class="summary-card"><div class="summary-label">峰值</div><div class="summary-value">¥${fmtM(s.peak_assets||s.total_assets)}</div><div class="summary-sub">回撤 ${(s.drawdown_pct||0).toFixed(2)}%</div></div>`;
}

function renderPositionsTable(d) {
  const t = document.getElementById('positionsBody');
  const h = d.holdings || [];
  if (!h.length) { t.innerHTML = '<tr><td colspan="10" class="placeholder">空仓</td></tr>'; return; }
  const tt = {cashcow:'<span class="tag tag-cashcow">🐮现金牛</span>',growth:'<span class="tag tag-growth">🚀成长</span>'};
  t.innerHTML = h.map(x => {
    const pc = (x.pnl||0)>=0?'up':'down', sg = (x.pnl||0)>=0?'+':'';
    return `<tr><td>${x.code}</td><td class="name-cell">${x.name}</td><td>${x.shares}</td><td>${fmtP(x.avg_cost)}</td><td>¥${fmtM(x.cost)}</td><td>${fmtP(x.current_price)}</td><td>¥${fmtM(x.market_value)}</td><td class="${pc}">${sg}¥${fmtM(Math.abs(x.pnl||0))}</td><td class="${pc}">${sg}${(x.pnl_pct||0).toFixed(2)}%</td><td>${tt[x.type]||x.type}</td></tr>`;
  }).join('');
}

function renderRedlines(d) {
  const el = document.getElementById('redlineGrid');
  const rl = d.redlines || [];
  if (!rl.length) { el.innerHTML = '<p class="placeholder">--</p>'; return; }
  el.innerHTML = rl.map(r => `<div class="redline-item ${r.status==='warn'?'warn':r.status==='danger'?'danger':''}"><span class="redline-label">${r.name}</span><span class="redline-value">${r.status==='ok'?'✅':r.status==='warn'?'⚠️':'🔴'} ${r.value} / ${r.limit}</span></div>`).join('');
}

function renderTrades(d) {
  const t = document.getElementById('tradesBody');
  const tr = d.trades || [];
  if (!tr.length) { t.innerHTML = '<tr><td colspan="7" class="placeholder">暂无</td></tr>'; return; }
  t.innerHTML = tr.map(x => `<tr><td>${x.date}</td><td>${x.action==='BUY'?'<span class="tag tag-buy">买入</span>':'<span class="tag tag-sell">卖出</span>'}</td><td>${x.code}</td><td class="name-cell">${x.name}</td><td>${x.shares}</td><td>${fmtP(x.price)}</td><td>¥${fmtM(x.amount)}</td></tr>`).join('');
}

function renderReview(d) {
  const el = document.getElementById('reviewList');
  const entries = d.entries || [];
  document.getElementById('reviewCount').textContent = `${entries.length} 条`;
  if (!entries.length) { el.innerHTML = '<p class="placeholder">暂无复盘记录</p>'; return; }

  el.innerHTML = entries.map(e => {
    const sc = {'green':'state-risk-on','orange':'state-neutral','red':'state-risk-off'};
    let sigHtml = '';
    if (e.signals?.length) {
      sigHtml = e.signals.map(s => {
        const lvl = s.level === 'danger' ? 'sig-danger' : s.level === 'warn' ? 'sig-warn' : s.level === 'positive' ? 'sig-positive' : 'sig-info';
        return `<div class="signal-row ${lvl}"><span>${s.icon}</span> <span>${s.text}</span></div>`;
      }).join('');
    }

    let scrHtml = '';
    if (e.screening) {
      scrHtml = `<div class="rv-block"><div class="rv-label">🔎 筛股</div><span class="rv-tag">现金牛 ${e.screening.cashcow||0}</span><span class="rv-tag">成长股 ${e.screening.growth||0}</span>${e.screening.note?`<span class="rv-note">${e.screening.note}</span>`:''}</div>`;
    }

    return `<div class="review-card">
      <div class="rc-header"><span class="rc-type">${e.type_icon||''} ${e.type}</span><span class="state-badge-sm ${sc[e.state_color]||'state-neutral'}">${e.market_state}</span><span class="rc-time">${e.datetime}</span></div>
      <div class="rc-body">${sigHtml?`<div class="rv-block"><div class="rv-label">🚨 触发信号</div>${sigHtml}</div>`:''}${scrHtml}<div class="rv-block"><div class="rv-label">💡 决策</div><div class="rv-text">${e.decisions}</div></div></div>
    </div>`;
  }).join('');
}

// === Auto Refresh ===
function startAutoRefresh() {
  refreshTimer = setInterval(loadAllData, CONFIG.refreshInterval);
  countdownTimer = setInterval(() => {
    secondsLeft--; if (secondsLeft <= 0) secondsLeft = CONFIG.refreshInterval / 1000;
    document.getElementById('refreshInfo').textContent = `刷新 ${secondsLeft}s`;
  }, 1000);
}

function updateTimestamp(ts) {
  document.getElementById('updateTime').textContent = `📡 ${ts||'--'}`;
  document.getElementById('dataTimestamp').textContent = `更新: ${ts||'--'}`;
}

// === Helpers ===
function fmtP(v) { if (v==null||isNaN(v)) return '--'; return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2); }
function fmtM(v) { if (v==null||isNaN(v)) return '--'; return Math.abs(v)>=10000 ? (v/10000).toFixed(2)+'万' : v.toFixed(0); }