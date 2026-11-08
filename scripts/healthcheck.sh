#!/usr/bin/env bash
set -euo pipefail

DEPLOY_PORT="${DEPLOY_PORT:-8010}"
BASE="http://127.0.0.1:${DEPLOY_PORT}"
FAILED=0

check_status() {
  local label="$1"
  local url="$2"
  local expected="$3"
  local code
  code="$(curl -sS -o /dev/null -m 8 -w '%{http_code}' "$url" || true)"
  if [ "$code" = "$expected" ]; then
    echo "PASS  $label  HTTP $code  $url"
  else
    echo "FAIL  $label  expected $expected got $code  $url" >&2
    FAILED=1
  fi
}

check_status "login page" "$BASE/accounts/login/" "200"
check_status "static css" "$BASE/static/css/app.css" "200"
check_status "workbench css" "$BASE/static/css/workbench.css" "200"
check_status "knowledge page (unauthenticated redirect)" "$BASE/knowledge/" "302"
check_status "workbench page (unauthenticated redirect)" "$BASE/workbench/" "302"
check_status "capability API (unauthenticated)" "$BASE/api/v1/platform/capabilities/" "401"
check_status "workbench status API (unauthenticated)" "$BASE/api/v1/workbench/status/" "401"

if [ "$FAILED" -ne 0 ]; then
  echo "健康检查失败" >&2
  exit 1
fi
echo "健康检查通过：$BASE"
