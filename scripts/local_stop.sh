#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/Volumes/半岛铁盒/实验室考核部署}"
RUN_DIR="$DEPLOY_DIR/data/run"

stop_one() {
  local pid_file="$1"
  local label="$2"
  local pattern="$3"
  if [ ! -f "$pid_file" ]; then
    echo "${label}：没有记录 PID。"
    return 0
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    echo "${label}：进程已不存在（PIDs $pid）。"
    rm -f "$pid_file"
    return 0
  fi
  local command
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  if [[ "$command" != *"$pattern"* ]]; then
    echo "${label}：PID ${pid} 的命令不匹配，拒绝停止：${command}" >&2
    return 1
  fi
  local cwd
  cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | awk -F'n' '/^n/{print $2; exit}')"
  if [ -n "$cwd" ] && [ "$cwd" != "$DEPLOY_DIR" ]; then
    echo "${label}：PID ${pid} 的工作目录不是部署目录（${cwd}），拒绝停止。" >&2
    return 1
  fi
  echo "${label}：停止 PID ${pid}（${command}）"
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "${label}：TERM 未退出，发送 KILL 仅针对该 PID。" >&2
    kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

stop_one "$RUN_DIR/worker.pid" "任务 worker" "manage.py workbench_worker" || true
stop_one "$RUN_DIR/server.pid" "Web 服务" "manage.py runserver" || true
echo "已停止本项目记录的进程；未使用全局 pkill。"
