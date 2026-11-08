#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/Volumes/半岛铁盒/实验室考核部署}"
VENV_PYTHON="${VENV_PYTHON:-/Volumes/半岛铁盒/实验室/.venv/bin/python}"
PYTHONPATH_RUNTIME="${PYTHONPATH_RUNTIME:-/Volumes/半岛铁盒/实验室/runtime}"

if [ ! -d "$DEPLOY_DIR" ] || [ ! -f "$DEPLOY_DIR/.env" ]; then
  echo "部署目录或 .env 不存在，请先运行 scripts/local_setup.sh" >&2
  exit 1
fi
if [ ! -x "$VENV_PYTHON" ]; then
  echo "VENV_PYTHON 不可执行：$VENV_PYTHON" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. "$DEPLOY_DIR/.env"
set +a
export PYTHONPATH="${PYTHONPATH_RUNTIME}${PYTHONPATH:+:$PYTHONPATH}"

RUN_DIR="$DEPLOY_DIR/data/run"
mkdir -p "$RUN_DIR"
SERVER_PID_FILE="$RUN_DIR/server.pid"
WORKER_PID_FILE="$RUN_DIR/worker.pid"
SERVER_LOG="$RUN_DIR/server.log"
WORKER_LOG="$RUN_DIR/worker.log"
PORT_FILE="$RUN_DIR/port.txt"

port_busy() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

existing_process() {
  [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null
}

if existing_process "$SERVER_PID_FILE"; then
  PORT="$(cat "$PORT_FILE" 2>/dev/null || echo "${DEPLOY_PORT:-8010}")"
  echo "Web 服务已在运行，PID=$(cat "$SERVER_PID_FILE")，URL=http://127.0.0.1:${PORT}/"
else
  PORT="${DEPLOY_PORT:-8010}"
  if port_busy "$PORT"; then
    echo "端口 $PORT 已被其他进程占用，不终止占用者；自动选择替代端口。"
    FOUND=""
    for candidate in $(seq 8020 8099); do
      if ! port_busy "$candidate"; then FOUND="$candidate"; break; fi
    done
    if [ -z "$FOUND" ]; then
      echo "没有可用端口（8020-8099）。" >&2
      exit 1
    fi
    PORT="$FOUND"
  fi
  echo "$PORT" > "$PORT_FILE"
  cd "$DEPLOY_DIR"
  PORT="$PORT" "$VENV_PYTHON" - "$VENV_PYTHON" "$DEPLOY_DIR" "$PORT" "$SERVER_LOG" "$SERVER_PID_FILE" <<'PY'
import os, subprocess, sys
python, cwd, port, log, pid_file = sys.argv[1:6]
with open(log, 'ab') as handle:
    process = subprocess.Popen(
        [python, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload', '--insecure'],
        cwd=cwd, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT,
        start_new_session=True, env=os.environ.copy(),
    )
open(pid_file, 'w').write(str(process.pid))
print(process.pid)
PY
fi

if existing_process "$WORKER_PID_FILE"; then
  echo "任务 worker 已在运行，PID=$(cat "$WORKER_PID_FILE")"
else
  cd "$DEPLOY_DIR"
  "$VENV_PYTHON" - "$VENV_PYTHON" "$DEPLOY_DIR" "$WORKER_LOG" "$WORKER_PID_FILE" <<'PY'
import os, subprocess, sys
python, cwd, log, pid_file = sys.argv[1:5]
with open(log, 'ab') as handle:
    process = subprocess.Popen(
        [python, 'manage.py', 'workbench_worker', '--poll', '2'],
        cwd=cwd, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT,
        start_new_session=True, env=os.environ.copy(),
    )
open(pid_file, 'w').write(str(process.pid))
print('worker pid:', process.pid)
PY
fi

SERVER_PID="$(cat "$SERVER_PID_FILE" 2>/dev/null || true)"
WORKER_PID="$(cat "$WORKER_PID_FILE" 2>/dev/null || true)"
HEALTH_URL="http://127.0.0.1:${PORT}/accounts/login/"
WORKBENCH_URL="http://127.0.0.1:${PORT}/workbench/"
CODE=""
for _ in $(seq 1 30); do
  CODE="$(curl -sS -o /dev/null -m 3 -w '%{http_code}' "$HEALTH_URL" || true)"
  if [ "$CODE" = "200" ]; then break; fi
  sleep 0.5
done
if [ "$CODE" != "200" ]; then
  echo "Web 服务未通过健康检查（HTTP ${CODE}），日志：${SERVER_LOG}" >&2
  tail -30 "$SERVER_LOG" >&2 || true
  exit 1
fi

echo "本地服务已启动"
echo "URL：http://127.0.0.1:${PORT}/"
echo "工作台：$WORKBENCH_URL"
echo "端口：$PORT"
echo "Web PID：${SERVER_PID:-unknown}（${SERVER_PID_FILE}）"
echo "Worker PID：${WORKER_PID:-unknown}（${WORKER_PID_FILE}）"
echo "日志：${SERVER_LOG}；${WORKER_LOG}"
echo "Health：${HEALTH_URL}"
echo "停止：${DEPLOY_DIR}/scripts/local_stop.sh"
echo "回滚：${RUN_DIR}/ROLLBACK.txt（若存在）或使用 data/backups 下的数据库快照"
