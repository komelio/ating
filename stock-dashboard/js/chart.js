/* === K线图组件 v3 - 稳健Canvas蜡烛图 === */
const ChartModule = (() => {
  let currentCode = '', currentPeriod = 'daily', chartData = null;
  let canvas, ctx;

  const C = {
    bg:'#0d1117', grid:'#1c2333', tx:'#6e7681',
    up:'#f85149', dn:'#3fb950',
    m5:'#f0883e', m10:'#58a6ff', m20:'#a371f7', m60:'#e3b341',
  };

  function calcMA(data, n) {
    const r = new Array(data.length).fill(null);
    for (let i = n - 1; i < data.length; i++) {
      let s = 0; for (let j = 0; j < n; j++) s += data[i - j].close;
      r[i] = s / n;
    }
    return r;
  }

  function draw() {
    if (!canvas || !chartData) return;
    const klines = chartData[currentPeriod];
    if (!klines || !klines.length) { drawMsg('暂无K线数据'); return; }

    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (w <= 0 || h <= 0) { drawMsg('加载中...'); return; }

    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const P = { t: 16, r: 12, b: 30, l: 72 };
    const vGap = 14;
    const mH = (h - P.t - P.b - vGap) * 0.66;
    const vH = (h - P.t - P.b - vGap) * 0.28;

    const barW = 5;
    const maxN = Math.max(10, Math.floor((w - P.l - P.r) / barW));
    const off = Math.max(0, klines.length - maxN);
    const data = klines.slice(off);
    const n = data.length;
    const xS = (w - P.l - P.r) / n;

    let pMin = Infinity, pMax = -Infinity, vMax = 0;
    for (const d of data) {
      if (d.high > pMax) pMax = d.high; if (d.low < pMin) pMin = d.low;
      if (d.volume > vMax) vMax = d.volume;
    }
    const pad = (pMax - pMin) * 0.06 || 0.1;
    pMin -= pad; pMax += pad;
    const pRng = pMax - pMin || 1;

    // Clear
    ctx.fillStyle = C.bg; ctx.fillRect(0, 0, w, h);

    // Grid
    ctx.strokeStyle = C.grid; ctx.lineWidth = 0.5;
    ctx.fillStyle = C.tx; ctx.font = '10px monospace';
    for (let i = 0; i <= 6; i++) {
      const y = P.t + mH * (1 - i / 6);
      ctx.beginPath(); ctx.moveTo(P.l, y); ctx.lineTo(w - P.r, y); ctx.stroke();
      if (i % 2 === 0) { ctx.textAlign = 'right'; ctx.fillText((pMin + pRng * i / 6).toFixed(2), P.l - 6, y + 4); }
    }
    ctx.textAlign = 'center';
    const step = Math.max(1, Math.floor(n / 5));
    for (let i = 0; i < n; i += step) {
      const d = data[i].date;
      ctx.fillText(d.length >= 10 ? d.slice(5) : d, P.l + i * xS + xS / 2, h - P.b + 16);
    }

    // Volume
    const cW = Math.max(1, xS * 0.7);
    for (let i = 0; i < n; i++) {
      const d = data[i];
      const vh2 = vMax > 0 ? (d.volume / vMax) * vH : 0;
      ctx.fillStyle = d.close >= d.open ? C.up : C.dn;
      ctx.globalAlpha = 0.45;
      const vTop = P.t + mH + vGap;
      ctx.fillRect(P.l + i * xS + (xS - cW) / 2, vTop + vH - vh2, cW, vh2);
      ctx.globalAlpha = 1;
    }

    // MA
    const mas = [{n:5,c:C.m5},{n:10,c:C.m10},{n:20,c:C.m20},{n:60,c:C.m60}];
    for (const ma of mas) {
      const vals = calcMA(klines, ma.n);
      ctx.strokeStyle = ma.c; ctx.lineWidth = 1.5; ctx.beginPath();
      let started = false;
      for (let i = off; i < klines.length; i++) {
        const v = vals[i]; if (v == null) continue;
        const x = P.l + (i - off) * xS + xS / 2;
        const y = P.t + mH * (1 - (v - pMin) / pRng);
        if (!started) { ctx.moveTo(x, y); started = true; }
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    // Candles
    for (let i = 0; i < n; i++) {
      const d = data[i];
      const x = P.l + i * xS + xS / 2;
      const isUp = d.close >= d.open;
      const yO = P.t + mH * (1 - (d.open - pMin) / pRng);
      const yC = P.t + mH * (1 - (d.close - pMin) / pRng);
      const yH = P.t + mH * (1 - (d.high - pMin) / pRng);
      const yL = P.t + mH * (1 - (d.low - pMin) / pRng);

      ctx.strokeStyle = isUp ? C.up : C.dn; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, yH); ctx.lineTo(x, yL); ctx.stroke();

      ctx.fillStyle = isUp ? C.up : C.dn;
      const bodyT = Math.min(yO, yC);
      const bodyH = Math.max(1, Math.abs(yC - yO));
      ctx.fillRect(x - cW / 2, bodyT, cW, bodyH);
    }

    // Vol label + legend
    ctx.fillStyle = C.tx; ctx.font = '10px monospace'; ctx.textAlign = 'left';
    ctx.fillText('VOL', P.l, P.t + mH + vGap + 10);
    updateLegend(data);
  }

  function drawMsg(msg) {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (w <= 0 || h <= 0) return;
    canvas.width = w; canvas.height = h;
    ctx.fillStyle = C.bg; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = C.tx; ctx.font = '14px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(msg, w / 2, h / 2);
  }

  function updateLegend(visible) {
    const el = document.getElementById('chartLegend');
    if (!visible.length) { el.innerHTML = ''; return; }
    const last = visible[visible.length - 1];
    const prev = visible.length > 1 ? visible[visible.length - 2] : last;
    const chg = last.close - prev.close;
    const chgP = prev.close ? (last.close / prev.close - 1) * 100 : 0;
    const sgn = chg >= 0 ? '+' : '';
    const clr = chg >= 0 ? C.up : C.dn;
    el.innerHTML = `<span style="color:#aaa">O:</span><b>${last.open.toFixed(2)}</b>
      <span style="color:#aaa"> H:</span><b>${last.high.toFixed(2)}</b>
      <span style="color:#aaa"> L:</span><b>${last.low.toFixed(2)}</b>
      <span style="color:${clr}"> C:</span><b style="color:${clr}">${last.close.toFixed(2)}</b>
      <span style="color:${clr};font-size:11px"> ${sgn}${chg.toFixed(2)} (${sgn}${chgP.toFixed(2)}%)</span>
      <span style="margin-left:14px;font-size:11px">
        <span style="color:${C.m5}">━MA5</span>
        <span style="color:${C.m10}">━MA10</span>
        <span style="color:${C.m20}">━MA20</span>
        <span style="color:${C.m60}">━MA60</span></span>`;
  }

  async function load(code, period) {
    try {
      const resp = await fetch(`data/history/${code}.json`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      chartData = await resp.json();
      currentCode = code;
      currentPeriod = period;

      document.getElementById('chartTitle').textContent =
        `${chartData.code || code} ${chartData.name || ''} - ${period === 'daily' ? '日K' : '周K'}`;

      // Ensure canvas has dimensions before drawing
      const container = document.querySelector('.chart-container');
      canvas = document.getElementById('klineCanvas');

      if (container.clientHeight < 50) {
        canvas.style.height = '420px';
      } else {
        canvas.style.height = '100%';
      }
      canvas.style.width = '100%';

      // Wait for layout
      await new Promise(r => requestAnimationFrame(r));
      draw();
      
      // Retry once if still 0-size
      if (canvas.clientWidth <= 0 || canvas.clientHeight <= 0) {
        await new Promise(r => setTimeout(r, 100));
        draw();
      }
    } catch (e) {
      console.warn('Chart load error:', e);
      document.getElementById('chartTitle').textContent = `${code} - 数据加载失败`;
      document.getElementById('chartLegend').innerHTML = '';
      chartData = null;
    }
  }

  function open(code) {
    const modal = document.getElementById('chartModal');
    modal.classList.add('active');

    document.querySelectorAll('.chart-btn').forEach(b => b.classList.remove('active'));
    const dailyBtn = document.querySelector('.chart-btn[data-period="daily"]');
    if (dailyBtn) dailyBtn.classList.add('active');

    load(code, 'daily');
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
    draw();
  }

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
        draw();
      }
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  });

  return { open, close, switchPeriod };
})();