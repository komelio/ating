#!/bin/bash
# V3.1 Dashboard — 完整刷新管道: 采集 → SQLite → JSON → Git Push
# 用法: bash refresh.sh
set -e

REPO="$HOME/dashboard-git"
LOG="$REPO/refresh.log"

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG"; }

cd "$REPO"

# ── 1. Git Pull (先拉取远端最新，避免冲突) ──
log "🔄 Git pull"
git pull --rebase origin main 2>&1 | tee -a "$LOG" || log "⚠️ pull 失败(继续)"

# ── 2. 数据采集 → SQLite → JSON ──
log "📊 数据刷新"
python3 gen_data.py >> "$LOG" 2>&1

# ── 3. Commit & Push ──
log "📤 Git commit"
git add v3-dashboard/data/ gen_data.py
if git diff --cached --quiet; then
    log "✅ 无数据变更，跳过推送"
else
    git commit -m "📊 数据刷新 $(date '+%Y-%m-%d %H:%M')" 2>&1 | tee -a "$LOG"
    git push origin main 2>&1 | tee -a "$LOG"
    log "✅ 推送完成 → https://komelio.github.io/ating/v3-dashboard/index.html"
fi

echo "" >> "$LOG"