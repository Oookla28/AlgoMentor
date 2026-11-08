#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/Volumes/半岛铁盒/实验室考核部署}"
VENV_PYTHON="${VENV_PYTHON:-/Volumes/半岛铁盒/实验室/.venv/bin/python}"
PYTHONPATH_RUNTIME="${PYTHONPATH_RUNTIME:-/Volumes/半岛铁盒/实验室/runtime}"
RUN_DIR="$DEPLOY_DIR/data/run"

if [ -d "$DEPLOY_DIR" ] && [ -f "$DEPLOY_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$DEPLOY_DIR/.env"
  set +a
fi
export PYTHONPATH="${PYTHONPATH_RUNTIME}${PYTHONPATH:+:$PYTHONPATH}"
PORT="$(cat "$RUN_DIR/port.txt" 2>/dev/null || echo "${DEPLOY_PORT:-8010}")"

pid_state() {
  local file="$1" label="$2"
  if [ -f "$file" ] && kill -0 "$(cat "$file")" 2>/dev/null; then
    echo "${label}：运行中 PID=$(cat "$file")"
  else
    echo "${label}：未运行"
  fi
}
pid_state "$RUN_DIR/server.pid" "Web 服务"
pid_state "$RUN_DIR/worker.pid" "任务 worker"
echo "端口：$PORT"
echo "登录页：HTTP $(curl -sS -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:${PORT}/accounts/login/" || echo FAIL)"
echo "工作台：http://127.0.0.1:${PORT}/workbench/"
echo "静态 CSS：HTTP $(curl -sS -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:${PORT}/static/css/workbench.css" || echo FAIL)"

if [ -x "$VENV_PYTHON" ] && [ -d "$DEPLOY_DIR" ]; then
  cd "$DEPLOY_DIR"
  "$VENV_PYTHON" manage.py shell -c "
from apps.workspace.services.tasks import worker_status
from apps.platform.models import AgentRun
print('worker heartbeat:', worker_status())
print('queued:', AgentRun.objects.filter(status='QUEUED').count(),
      'running:', AgentRun.objects.filter(status='RUNNING').count(),
      'failed:', AgentRun.objects.filter(status='FAILED').count())
" 2>/dev/null || echo "数据库状态读取失败（服务可能未迁移）。"
fi

echo "最近 Web 日志："
tail -n 5 "$RUN_DIR/server.log" 2>/dev/null || echo "（无）"
echo "最近 worker 日志："
tail -n 5 "$RUN_DIR/worker.log" 2>/dev/null || echo "（无）"
