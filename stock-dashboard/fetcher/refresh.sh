#!/bin/bash
# 小智盯盘 - 数据刷新 & 自动推送脚本
# 由 cron / OpenClaw 定时任务调用

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
REPO_DIR="$PROJECT_DIR"
LOG_FILE="$PROJECT_DIR/fetcher/refresh.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

cd "$PROJECT_DIR"

# 1. 拉取最新代码（防止冲突）
log "🔄 拉取远程更新..."
git pull --rebase origin main 2>&1 | tee -a "$LOG_FILE" || true

# 2. 运行数据抓取
log "📊 运行数据抓取..."
python3 fetcher/fetch_data.py refresh 2>&1 | tee -a "$LOG_FILE"

# 3. 如果是指定时间(收盘后)，额外运行分析
HOUR=$(date +%H)
if [ "$HOUR" -ge 15 ]; then
    log "📝 收盘后运行分析记录..."
    python3 fetcher/fetch_data.py analysis 2>&1 | tee -a "$LOG_FILE"
fi

# 4. 提交变更
if git diff --quiet && git diff --cached --quiet; then
    log "✅ 无数据变更，跳过提交"
else
    log "📦 提交数据更新..."
    git add data/
    git commit -m "📊 数据刷新 $(date '+%Y-%m-%d %H:%M')" 2>&1 | tee -a "$LOG_FILE"
    
    log "🚀 推送至 GitHub..."
    git push origin main 2>&1 | tee -a "$LOG_FILE"
    log "✅ 推送完成"
fi

echo "" >> "$LOG_FILE"