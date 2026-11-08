#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-/Volumes/半岛铁盒/实验室/AlgoMentor}"
DEPLOY_DIR="${DEPLOY_DIR:-/Volumes/半岛铁盒/实验室考核部署}"
VENV_PYTHON="${VENV_PYTHON:-/Volumes/半岛铁盒/实验室/.venv/bin/python}"
PYTHONPATH_RUNTIME="${PYTHONPATH_RUNTIME:-/Volumes/半岛铁盒/实验室/runtime}"
DEPLOY_PORT="${DEPLOY_PORT:-8010}"
CHROMA_PATH="${CHROMA_PATH:-/tmp/algomentor-deploy-chroma}"
DEMO_USERS="${DEMO_USERS:-true}"
DEMO_PASSWORD="${DEMO_PASSWORD:-demo-pass-2026}"

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR=""

if [ ! -d "$SOURCE_DIR" ]; then
  echo "SOURCE_DIR 不存在：$SOURCE_DIR" >&2
  exit 1
fi
if [ ! -x "$VENV_PYTHON" ]; then
  echo "VENV_PYTHON 不可执行：$VENV_PYTHON" >&2
  exit 1
fi

if [ -e "$DEPLOY_DIR" ]; then
  BACKUP_DIR="${DEPLOY_DIR}.backup.${STAMP}"
  echo "目标目录已存在，创建备份：$BACKUP_DIR"
  cp -a "$DEPLOY_DIR" "$BACKUP_DIR"
fi

mkdir -p "$DEPLOY_DIR" "$DEPLOY_DIR/data/run" "$DEPLOY_DIR/data/evidence_uploads"
rsync -a \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='data/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='._*' \
  --exclude='output/' \
  --exclude='knowledge/processed/*.joblib' \
  "$SOURCE_DIR/" "$DEPLOY_DIR/"

export PYTHONPATH="${PYTHONPATH_RUNTIME}${PYTHONPATH:+:$PYTHONPATH}"
export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-tfidf}"
export CHROMA_PATH
export RAG_MIN_SCORE="${RAG_MIN_SCORE:-0.2}"

cd "$DEPLOY_DIR"

"$VENV_PYTHON" manage.py check
"$VENV_PYTHON" manage.py makemigrations --check --dry-run
"$VENV_PYTHON" manage.py migrate --noinput
"$VENV_PYTHON" manage.py seed_knowledge
"$VENV_PYTHON" manage.py seed_problems
"$VENV_PYTHON" manage.py ingest_knowledge --advanced

if [ "$DEMO_USERS" = "true" ]; then
  DEMO_PASSWORD="$DEMO_PASSWORD" "$VENV_PYTHON" manage.py shell -c "
from django.contrib.auth import get_user_model
import os
User = get_user_model()
password = os.environ['DEMO_PASSWORD']
for username, staff in (('demo_student', False), ('demo_staff', True)):
    user, _ = User.objects.get_or_create(username=username)
    user.is_staff = staff
    user.set_password(password)
    user.save()
print('demo users ready: demo_student / demo_staff (local only)')
"
fi

SOURCE_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
SOURCE_BRANCH="$(git -C "$SOURCE_DIR" branch --show-current)"
SOURCE_DIRTY="$(git -C "$SOURCE_DIR" status --porcelain | wc -l | tr -d ' ')"

SOURCE_DIR="$SOURCE_DIR" DEPLOY_DIR="$DEPLOY_DIR" SOURCE_COMMIT="$SOURCE_COMMIT" \
SOURCE_BRANCH="$SOURCE_BRANCH" SOURCE_DIRTY="$SOURCE_DIRTY" DEPLOY_PORT="$DEPLOY_PORT" \
CHROMA_PATH="$CHROMA_PATH" BACKUP_DIR="$BACKUP_DIR" VENV_PYTHON="$VENV_PYTHON" \
"$VENV_PYTHON" - <<'PY'
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

source = Path(os.environ['SOURCE_DIR'])
target = Path(os.environ['DEPLOY_DIR'])
config = {
    'embedding_provider': os.environ.get('EMBEDDING_PROVIDER', 'tfidf'),
    'chroma_path': os.environ.get('CHROMA_PATH', ''),
    'rag_min_score': os.environ.get('RAG_MIN_SCORE', '0.2'),
    'port': os.environ.get('DEPLOY_PORT', '8010'),
    'source_commit': os.environ.get('SOURCE_COMMIT', ''),
    'source_branch': os.environ.get('SOURCE_BRANCH', ''),
}
config_hash = hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
manifest = {
    'source_path': str(source),
    'source_commit': os.environ.get('SOURCE_COMMIT', ''),
    'source_branch': os.environ.get('SOURCE_BRANCH', ''),
    'source_dirty_files': int(os.environ.get('SOURCE_DIRTY', '0') or 0),
    'target_path': str(target),
    'created_at': datetime.now(timezone.utc).isoformat(),
    'config': config,
    'config_hash': config_hash,
    'backup_path': os.environ.get('BACKUP_DIR', ''),
    'venv_python': os.environ.get('VENV_PYTHON', ''),
    'capabilities': {
        'embedding': 'fallback: tfidf (not BGE)',
        'advanced_index': 'available if ingest succeeded',
        'reranker': 'deterministic',
        'llm': 'not-configured: per-user BYOK',
        'piston': 'environment-limited unless localhost:2000 is open',
        'ocr': 'disabled unless optional deps installed',
        'asr': 'disabled unless optional deps installed',
        'keyframes': 'disabled unless ffmpeg installed',
    },
    'notes': [
        'Do not expose this demo server to the public internet.',
        'Chroma is stored outside the external volume because of SQLite locking limits.',
        'BGE, cross-encoder, OCR, ASR, keyframes and Piston remain unverified.',
    ],
}
text = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
(target / '.deployment-manifest.json').write_text(text, encoding='utf-8')
(source / '.deployment-manifest.json').write_text(text, encoding='utf-8')
print(json.dumps({'manifest': str(target / '.deployment-manifest.json'), 'config_hash': config_hash}, ensure_ascii=False))
PY

cat > "$DEPLOY_DIR/DEPLOYMENT_REPORT.md" <<EOF
# 本地部署报告

- 源目录：\`$SOURCE_DIR\`
- 部署目录：\`$DEPLOY_DIR\`
- 源提交：\`$SOURCE_COMMIT\`（分支 \`$SOURCE_BRANCH\`，未提交文件数 ${SOURCE_DIRTY}）
- 创建时间：$(date '+%Y-%m-%d %H:%M:%S %Z')
- 端口：\`$DEPLOY_PORT\`
- Chroma：\`$CHROMA_PATH\`
- 备份：\`${BACKUP_DIR:-无（首次部署）}\`

## 已验证

- \`manage.py check\`
- \`makemigrations --check --dry-run\`
- \`migrate --noinput\`
- \`seed_knowledge\` / \`seed_problems\`
- \`ingest_knowledge --advanced\`（TF-IDF 2048 维）
- 演示账号（仅本机）：\`demo_student\` / \`demo_staff\`

## 启动与停止

\`\`\`bash
bash scripts/run_local.sh
bash scripts/healthcheck.sh
kill "\$(cat $DEPLOY_DIR/data/run/server.pid)"
\`\`\`

## 回滚

$(if [ -n "$BACKUP_DIR" ]; then echo "\`\`\`bash
mv \"$DEPLOY_DIR\" \"$DEPLOY_DIR.failed\"
mv \"$BACKUP_DIR\" \"$DEPLOY_DIR\"
\`\`\`"; else echo "首次部署，无备份可回滚；可直接停止服务并保留目录。"; fi)

## 未验证

BGE 高级索引、Cross-Encoder、LLM 在线生成、OCR、ASR、关键帧、本机 Piston、手机实机、生产安全审计。
EOF

cat > "$DEPLOY_DIR/data/run/ROLLBACK.txt" <<EOF
# 回滚命令（保留失败目录，不删除用户数据）
$(if [ -n "$BACKUP_DIR" ]; then echo "mv \"$DEPLOY_DIR\" \"$DEPLOY_DIR.failed\""; echo "mv \"$BACKUP_DIR\" \"$DEPLOY_DIR\""; else echo "# 首次部署：停止服务并保留 $DEPLOY_DIR"; fi)
EOF

cp "$DEPLOY_DIR/DEPLOYMENT_REPORT.md" "$SOURCE_DIR/DEPLOYMENT_REPORT.md"

echo "部署完成：$DEPLOY_DIR"
echo "启动：bash $DEPLOY_DIR/scripts/run_local.sh"
echo "健康检查：bash $DEPLOY_DIR/scripts/healthcheck.sh"
echo "报告：$DEPLOY_DIR/DEPLOYMENT_REPORT.md"
