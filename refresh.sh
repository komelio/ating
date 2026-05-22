#!/bin/bash
# V3.1 Dashboard — 完整刷新管道: 采集 → SQLite → JSON → Git Push
# 用法: bash refresh.sh
set -e

REPO="$HOME/dashboard-git"
LOG="$REPO/refresh.log"

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG"; }

cd "$REPO"

export GIT_SSL_NO_VERIFY=1

# ── 1. Git Pull (先拉取远端最新，避免冲突) ──
log "🔄 Git pull"
git pull --rebase origin main 2>&1 | tee -a "$LOG" || log "⚠️ pull 失败(继续)"

# ── 2. 数据采集 → SQLite → JSON ──
log "📊 数据刷新"
python3 gen_data.py >> "$LOG" 2>&1

# ── 3. Commit & Push ──
log "📤 Git commit"
git add v3-dashboard/data/ v3-dashboard/index.html gen_data.py
if git diff --cached --quiet; then
    log "✅ 无数据变更，跳过推送"
else
    git commit -m "📊 数据刷新 $(date '+%Y-%m-%d %H:%M')" 2>&1 | tee -a "$LOG"
    git push origin main 2>&1 | tee -a "$LOG"
    log "✅ 推送完成 → https://komelio.github.io/ating/v3-dashboard/index.html"
fi

# ── 4. 线上数据验证 ──
log "🔍 线上数据验证"
CHECK_URLS=(
    "https://komelio.github.io/ating/v3-dashboard/data/stocks.json"
    "https://komelio.github.io/ating/v3-dashboard/data/market.json"
    "https://komelio.github.io/ating/v3-dashboard/data/portfolio.json"
    "https://komelio.github.io/ating/v3-dashboard/data/analysis.json"
)
ALL_OK=true
for url in "${CHECK_URLS[@]}"; do
    HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        log "  ✅ $(basename "$url")"
    else
        log "  ❌ $(basename "$url") — HTTP $HTTP_CODE"
        ALL_OK=false
    fi
done
if $ALL_OK; then
    log "🎯 全部接口验证通过"
else
    log "⚠️ 部分接口异常，请检查"
fi

echo "" >> "$LOG"