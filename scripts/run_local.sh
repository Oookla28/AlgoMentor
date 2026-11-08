#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/Volumes/半岛铁盒/实验室考核部署}"
VENV_PYTHON="${VENV_PYTHON:-/Volumes/半岛铁盒/实验室/.venv/bin/python}"
PYTHONPATH_RUNTIME="${PYTHONPATH_RUNTIME:-/Volumes/半岛铁盒/实验室/runtime}"
DEPLOY_PORT="${DEPLOY_PORT:-8010}"
CHROMA_PATH="${CHROMA_PATH:-/tmp/algomentor-deploy-chroma}"

if [ ! -d "$DEPLOY_DIR" ]; then
  echo "DEPLOY_DIR 不存在：$DEPLOY_DIR" >&2
  exit 1
fi
if [ ! -x "$VENV_PYTHON" ]; then
  echo "VENV_PYTHON 不可执行：$VENV_PYTHON" >&2
  exit 1
fi

RUN_DIR="$DEPLOY_DIR/data/run"
mkdir -p "$RUN_DIR"
PID_FILE="$RUN_DIR/server.pid"
LOG_FILE="$RUN_DIR/server.log"
HEALTH_URL="http://127.0.0.1:${DEPLOY_PORT}/accounts/login/"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "服务已在运行，PID=$(cat "$PID_FILE")"
  echo "URL：http://127.0.0.1:${DEPLOY_PORT}/"
  echo "日志：$LOG_FILE"
  exit 0
fi

export PYTHONPATH="${PYTHONPATH_RUNTIME}${PYTHONPATH:+:$PYTHONPATH}"
export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-tfidf}"
export CHROMA_PATH
export RAG_MIN_SCORE="${RAG_MIN_SCORE:-0.2}"

cd "$DEPLOY_DIR"
nohup "$VENV_PYTHON" manage.py runserver "127.0.0.1:${DEPLOY_PORT}" --noreload >"$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

sleep 3
if ! kill -0 "$PID" 2>/dev/null; then
  echo "服务启动失败，日志：$LOG_FILE" >&2
  tail -40 "$LOG_FILE" >&2 || true
  exit 1
fi

echo "本地服务已启动"
echo "URL：http://127.0.0.1:${DEPLOY_PORT}/"
echo "端口：${DEPLOY_PORT}"
echo "PID：${PID}"
echo "日志：${LOG_FILE}"
echo "Health：${HEALTH_URL}"
echo "停止：kill \"\$(cat ${PID_FILE})\""
echo "回滚：cat ${RUN_DIR}/ROLLBACK.txt"
