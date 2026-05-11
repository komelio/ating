#!/bin/bash
# 小智盯盘 - 自动刷新 & 推送到 GitHub
set -e

WORKSPACE="/Users/mac/.openclaw/workspace/stock-dashboard"
GIT_REPO="/tmp/ating-clone"
LOG="$WORKSPACE/fetcher/refresh.log"

# Load token from separate config file (not committed)
ENV_FILE="$WORKSPACE/fetcher/.env"
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi
REMOTE="${GIT_REMOTE:-https://github.com/komelio/ating.git}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

# 1. 运行数据抓取（在workspace生成JSON）
log "📊 抓取数据..."
cd "$WORKSPACE"
python3 fetcher/fetch_data.py refresh >> "$LOG" 2>&1

# 2. 收盘后运行分析
HOUR=$(date +%H)
if [ "$HOUR" -ge 15 ]; then
    log "📝 收盘后分析..."
    python3 fetcher/fetch_data.py analysis >> "$LOG" 2>&1
fi

# 3. 同步到Git仓库并推送
log "🔄 同步到Git..."
if [ ! -d "$GIT_REPO" ]; then
    git clone "$REMOTE" "$GIT_REPO" 2>/dev/null
fi
cd "$GIT_REPO"
git pull --rebase origin main 2>&1 | tee -a "$LOG" || true

# Copy all updated content from workspace
cp -r "$WORKSPACE/data" "$GIT_REPO/stock-dashboard/"
cp -r "$WORKSPACE/js" "$GIT_REPO/stock-dashboard/" 2>/dev/null
cp "$WORKSPACE/index.html" "$GIT_REPO/stock-dashboard/" 2>/dev/null
cp "$WORKSPACE/css/style.css" "$GIT_REPO/stock-dashboard/css/" 2>/dev/null
cp "$WORKSPACE/fetcher/fetch_data.py" "$GIT_REPO/stock-dashboard/fetcher/" 2>/dev/null

git add stock-dashboard/data/ stock-dashboard/fetcher/fetch_data.py stock-dashboard/js/ stock-dashboard/css/ stock-dashboard/index.html
if git diff --cached --quiet; then
    log "✅ 无变更"
else
    git commit -m "📊 数据刷新 $(date '+%Y-%m-%d %H:%M')" 2>&1 | tee -a "$LOG"
    git push origin main 2>&1 | tee -a "$LOG"
    log "✅ 推送完成"
fi

echo "" >> "$LOG"