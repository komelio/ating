/* === K线图组件 - Canvas蜡烛图 v2 === */

const ChartModule = (() => {
  let currentCode = '';
  let currentPeriod = 'daily';
  let chartData = null;
  let canvas, ctx;

  const COLORS = {
    bg: '#0d1117', grid: '#1c2333', text: '#6e7681',
    up: '#f85149', down: '#3fb950',
    ma5: '#f0883e', ma10: '#58a6ff', ma20: '#a371f7', ma60: '#e3b341',
  };

  function calcMA(data, period) {
    const r = new Array(data.length).fill(null);
    for (let i = period - 1; i < data.length; i++) {
      let s = 0;
      for (let j = 0; j < period; j++) s += data[i - j].close;
      r[i] = s / period;
    }
    return r;
  }

  function renderChart() {
    if (!canvas || !chartData) return;
    const klines = chartData[currentPeriod] || [];
    if (!klines.length) return drawEmpty();

    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (w <= 0 || h <= 0) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    // Layout
    const P = { t: 16, r: 10, b: 28, l: 66 };
    const volGap = 12;
    const mainH = (h - P.t - P.b - volGap) * 0.68;
    const volH = (h - P.t - P.b - volGap) * 0.28;

    // Visible window
    const barW = 4;
    const maxBars = Math.max(10, Math.floor((w - P.l - P.r) / barW));
    const offset = Math.max(0, klines.length - maxBars);
    const data = klines.slice(offset);
    const n = data.length;
    const xS = (w - P.l - P.r) / n;

    // Price range
    let pMin = Infinity, pMax = -Infinity;
    for (const d of data) { if (d.high > pMax) pMax = d.high; if (d.low < pMin) pMin = d.low; }
    const pad = (pMax - pMin) * 0.05 || 0.1;
    pMin -= pad; pMax += pad;
    const pRng = pMax - pMin || 1;

    // Volume max
    let vMax = 0;
    for (const d of data) { if (d.volume > vMax) vMax = d.volume; }

    // Clear
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, w, h);

    // --- Grid ---
    ctx.strokeStyle = COLORS.grid;
    ctx.lineWidth = 0.5;
    ctx.fillStyle = COLORS.text;
    ctx.font = '10px monospace';
    for (let i = 0; i <= 6; i++) {
      const y = P.t + mainH * (1 - i / 6);
      ctx.beginPath(); ctx.moveTo(P.l, y); ctx.lineTo(w - P.r, y); ctx.stroke();
      if (i % 2 === 0) {
        ctx.textAlign = 'right';
        ctx.fillText((pMin + pRng * i / 6).toFixed(2), P.l - 6, y + 4);
      }
    }

    // Date labels
    ctx.textAlign = 'center';
    const step = Math.max(1, Math.floor(n / 5));
    for (let i = 0; i < n; i += step) {
      const d = data[i].date;
      ctx.fillText(d.length >= 10 ? d.slice(5) : d, P.l + i * xS + xS / 2, h - P.b + 16);
    }

    // --- Volume bars ---
    const cW = Math.max(1, xS * 0.7);
    for (let i = 0; i < n; i++) {
      const d = data[i];
      const vh = vMax > 0 ? (d.volume / vMax) * volH : 0;
      const isUp = d.close >= d.open;
      ctx.fillStyle = isUp ? COLORS.up : COLORS.down;
      ctx.globalAlpha = 0.45;
      const volTop = P.t + mainH + volGap;
      ctx.fillRect(P.l + i * xS + (xS - cW) / 2, volTop + volH - vh, cW, vh);
      ctx.globalAlpha = 1;
    }

    // --- MA lines ---
    const mas = [
      { n: 5, c: COLORS.ma5 }, { n: 10, c: COLORS.ma10 },
      { n: 20, c: COLORS.ma20 }, { n: 60, c: COLORS.ma60 },
    ];
    for (const ma of mas) {
      const maVals = calcMA(klines, ma.n);
      ctx.strokeStyle = ma.c;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let started = false;
      for (let i = offset; i < klines.length; i++) {
        const v = maVals[i];
        if (v == null) continue;
        const x = P.l + (i - offset) * xS + xS / 2;
        const y = P.t + mainH * (1 - (v - pMin) / pRng);
        if (!started) { ctx.moveTo(x, y); started = true; }
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    // --- Candles ---
    for (let i = 0; i < n; i++) {
      const d = data[i];
      const x = P.l + i * xS + xS / 2;
      const isUp = d.close >= d.open;
      const yO = P.t + mainH * (1 - (d.open - pMin) / pRng);
      const yC = P.t + mainH * (1 - (d.close - pMin) / pRng);
      const yH = P.t + mainH * (1 - (d.high - pMin) / pRng);
      const yL = P.t + mainH * (1 - (d.low - pMin) / pRng);

      ctx.strokeStyle = isUp ? COLORS.up : COLORS.down;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, yH); ctx.lineTo(x, yL); ctx.stroke();

      ctx.fillStyle = isUp ? COLORS.up : COLORS.down;
      const bodyT = Math.min(yO, yC);
      const bodyH = Math.max(1, Math.abs(yC - yO));
      ctx.fillRect(x - cW / 2, bodyT, cW, bodyH);
    }

    // Volume label
    ctx.fillStyle = COLORS.text;
    ctx.font = '10px monospace';
    ctx.textAlign = 'left';
    ctx.fillText('VOL', P.l, P.t + mainH + volGap + 10);

    // --- Legend ---
    updateLegend(klines, data);
  }

  function drawEmpty() {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = COLORS.text;
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('暂无K线数据', canvas.clientWidth / 2, canvas.clientHeight / 2);
  }

  function updateLegend(allKlines, visible) {
    const el = document.getElementById('chartLegend');
    if (!visible.length) { el.innerHTML = ''; return; }
    const last = visible[visible.length - 1];
    const prev = visible.length > 1 ? visible[visible.length - 2] : last;
    const chg = last.close - prev.close;
    const chgPct = prev.close ? (last.close / prev.close - 1) * 100 : 0;
    const sign = chg >= 0 ? '+' : '';
    const clr = chg >= 0 ? COLORS.up : COLORS.down;
    el.innerHTML = `<span style="color:#aaa">O:</span><b>${last.open.toFixed(2)}</b>
      <span style="color:#aaa"> H:</span><b>${last.high.toFixed(2)}</b>
      <span style="color:#aaa"> L:</span><b>${last.low.toFixed(2)}</b>
      <span style="color:${clr}"> C:</span><b style="color:${clr}">${last.close.toFixed(2)}</b>
      <span style="color:${clr};font-size:11px"> ${sign}${chg.toFixed(2)} (${sign}${chgPct.toFixed(2)}%)</span>
      <span style="margin-left:14px;font-size:11px">
        <span style="color:${COLORS.ma5}">━MA5</span>
        <span style="color:${COLORS.ma10}">━MA10</span>
        <span style="color:${COLORS.ma20}">━MA20</span>
        <span style="color:${COLORS.ma60}">━MA60</span>
      </span>`;
  }

  async function loadChart(code, period) {
    try {
      const resp = await fetch(`data/history/${code}.json`);
      if (!resp.ok) throw new Error('No data');
      chartData = await resp.json();
      currentCode = code;
    } catch (e) {
      chartData = null;
      document.getElementById('chartTitle').textContent = `${code} - 暂无历史数据`;
      document.getElementById('chartLegend').innerHTML = '';
      return;
    }

    currentPeriod = period;
    document.getElementById('chartTitle').textContent =
      `${chartData.code || code} ${chartData.name || ''} - ${period === 'daily' ? '日K' : '周K'}`;
    
    // Wait for layout then render
    requestAnimationFrame(() => {
      requestAnimationFrame(renderChart);
    });
  }

  function open(code) {
    const modal = document.getElementById('chartModal');
    modal.classList.add('active');
    
    // Reset buttons
    document.querySelectorAll('.chart-btn').forEach(b => b.classList.remove('active'));
    const dailyBtn = document.querySelector('.chart-btn[data-period="daily"]');
    if (dailyBtn) dailyBtn.classList.add('active');

    // Size canvas to container
    const container = document.querySelector('.chart-container');
    canvas = document.getElementById('klineCanvas');
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    // Ensure container has dimensions
    if (container.clientHeight < 50) {
      canvas.style.height = '400px';
    }

    loadChart(code, 'daily');
  }

  function close() {
    document.getElementById('chartModal').classList.remove('active');
    chartData = null;
  }

  function switchPeriod(period) {
    if (!chartData) return;
    currentPeriod = period;
    document.querySelectorAll('.chart-btn').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`.chart-btn[data-period="${period}"]`);
    if (btn) btn.classList.add('active');
    document.getElementById('chartTitle').textContent =
      `${chartData.code} ${chartData.name || ''} - ${period === 'daily' ? '日K' : '周K'}`;
    requestAnimationFrame(() => requestAnimationFrame(renderChart));
  }

  // Init
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('chartClose').addEventListener('click', close);
    document.getElementById('chartModal').addEventListener('click', e => {
      if (e.target === document.getElementById('chartModal')) close();
    });
    document.querySelectorAll('.chart-btn').forEach(b => {
      b.addEventListener('click', () => switchPeriod(b.dataset.period));
    });
    window.addEventListener('resize', () => {
      if (chartData && document.getElementById('chartModal').classList.contains('active')) {
        requestAnimationFrame(() => requestAnimationFrame(renderChart));
      }
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  });

  return { open, close, switchPeriod };
})();