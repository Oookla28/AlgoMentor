#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-/Volumes/半岛铁盒/实验室/AlgoMentor}"
DEPLOY_DIR="${DEPLOY_DIR:-/Volumes/半岛铁盒/实验室考核部署}"
VENV_PYTHON="${VENV_PYTHON:-/Volumes/半岛铁盒/实验室/.venv/bin/python}"
PYTHONPATH_RUNTIME="${PYTHONPATH_RUNTIME:-/Volumes/半岛铁盒/实验室/runtime}"
DEPLOY_PORT="${DEPLOY_PORT:-8010}"
CHROMA_PATH="${CHROMA_PATH:-/tmp/algomentor-deploy-chroma}"
DEMO_USERNAME="${DEMO_USERNAME:-demo_student}"
RUN_TESTS="${RUN_TESTS:-true}"
STAMP="$(date +%Y%m%d_%H%M%S)"

if [ ! -d "$SOURCE_DIR" ]; then
  echo "SOURCE_DIR 不存在：$SOURCE_DIR" >&2
  exit 1
fi
if [ ! -x "$VENV_PYTHON" ]; then
  echo "VENV_PYTHON 不可执行：$VENV_PYTHON" >&2
  exit 1
fi

export PYTHONPATH="${PYTHONPATH_RUNTIME}${PYTHONPATH:+:$PYTHONPATH}"
export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-tfidf}"
export CHROMA_PATH
export RAG_MIN_SCORE="${RAG_MIN_SCORE:-0.2}"
export DEPLOY_PORT

mkdir -p "$DEPLOY_DIR" "$DEPLOY_DIR/data/run" "$DEPLOY_DIR/data/evidence_uploads" "$CHROMA_PATH"

# Stop only this project's recorded processes before touching code/migrations.
if [ -x "$DEPLOY_DIR/scripts/local_stop.sh" ]; then
  DEPLOY_DIR="$DEPLOY_DIR" VENV_PYTHON="$VENV_PYTHON" "$DEPLOY_DIR/scripts/local_stop.sh" || true
fi

# Consistent SQLite snapshot (never copy a live main file while WAL is active).
if [ -f "$DEPLOY_DIR/data/db.sqlite3" ]; then
  SNAPSHOT_DIR="$DEPLOY_DIR/data/backups/$STAMP"
  mkdir -p "$SNAPSHOT_DIR"
  "$VENV_PYTHON" - "$DEPLOY_DIR/data/db.sqlite3" "$SNAPSHOT_DIR/db.sqlite3" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()
src.close()
print('sqlite snapshot:', sys.argv[2])
PY
  echo "数据库快照：$SNAPSHOT_DIR/db.sqlite3"
fi

# Code-only sync: keep data/, .env and the existing fitted embedding vectorizer.
rsync -a \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='data/' \
  --exclude='.env' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='._*' \
  --exclude='.pytest_cache/' \
  --exclude='output/' \
  --exclude='knowledge/processed/*.joblib' \
  "$SOURCE_DIR/" "$DEPLOY_DIR/"

if [ ! -f "$DEPLOY_DIR/.env" ]; then
  cd "$DEPLOY_DIR"
  "$VENV_PYTHON" - "$DEPLOY_DIR" <<'PY'
import os, secrets, sys
from pathlib import Path
from cryptography.fernet import Fernet
root = Path(sys.argv[1])
text = (root / '.env.example').read_text(encoding='utf-8')
text = text.replace('DJANGO_SECRET_KEY=\n', 'DJANGO_SECRET_KEY=' + secrets.token_urlsafe(48) + '\n')
text = text.replace('APP_ENCRYPTION_KEY=\n', 'APP_ENCRYPTION_KEY=' + Fernet.generate_key().decode() + '\n')
text = text.replace('DJANGO_DEBUG=true', 'DJANGO_DEBUG=false')
text = text.replace('EMBEDDING_PROVIDER=bge', 'EMBEDDING_PROVIDER=tfidf')
text = text.replace('RAG_MIN_SCORE=0.45', 'RAG_MIN_SCORE=0.2')
text += '\n# Local preview only\nCHROMA_PATH=/tmp/algomentor-deploy-chroma\nDEPLOY_PORT=8010\n'
env = root / '.env'
env.write_text(text, encoding='utf-8')
env.chmod(0o600)
print('created .env with fresh local keys; keep it private')
PY
else
  echo ".env 已存在，保留原配置与加密主密钥。"
fi

cd "$DEPLOY_DIR"
set -a
# shellcheck disable=SC1091
. "$DEPLOY_DIR/.env"
set +a

"$VENV_PYTHON" manage.py check
"$VENV_PYTHON" manage.py makemigrations --check --dry-run
"$VENV_PYTHON" manage.py migrate --noinput

DOC_COUNT="$("$VENV_PYTHON" manage.py shell -c "from apps.knowledge.models import KnowledgeDocument; print(KnowledgeDocument.objects.count())" | tail -1)"
if [ "$DOC_COUNT" = "0" ]; then
  echo "知识库为空，执行首次课程初始化。"
  "$VENV_PYTHON" manage.py seed_knowledge || true
  "$VENV_PYTHON" manage.py seed_problems || true
  "$VENV_PYTHON" manage.py ingest_knowledge --advanced || true
else
  echo "知识库已有 $DOC_COUNT 份文档，跳过课程重建。"
fi

# Demo users are created only if missing; existing passwords are never reset.
"$VENV_PYTHON" manage.py shell -c "
from django.contrib.auth import get_user_model
from pathlib import Path
import secrets
User = get_user_model()
created = []
for username, staff in (('demo_student', False), ('demo_staff', True)):
    user = User.objects.filter(username=username).first()
    if user is None:
        password = secrets.token_urlsafe(18)
        user = User.objects.create_user(username=username, password=password, is_staff=staff)
        created.append((username, password))
    elif staff and not user.is_staff:
        user.is_staff = True
        user.save(update_fields=['is_staff'])
if created:
    path = Path('data/run/demo_credentials.txt')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(f'{name}: {password}' for name, password in created) + '\n', encoding='utf-8')
    path.chmod(0o600)
    print('demo credentials written to', path)
else:
    print('demo users already exist; passwords unchanged')
"

"$VENV_PYTHON" manage.py seed_workbench_demo --username "$DEMO_USERNAME" || true

if [ "$RUN_TESTS" = "true" ]; then
  echo "运行完整回归测试（会使用隔离测试数据库）..."
  "$VENV_PYTHON" -m pytest -q
fi

"$VENV_PYTHON" - "$SOURCE_DIR" "$DEPLOY_DIR" "$DEPLOY_PORT" "$CHROMA_PATH" <<'PY'
import hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

source, target, port, chroma = sys.argv[1:5]
os.chdir(target)
sys.path.insert(0, target)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import django
django.setup()

from apps.platform.capabilities import probe_capabilities
from apps.workspace.models import Workspace, WorkerHeartbeat
from apps.workspace.services.tasks import worker_status

source_commit = subprocess.run(
    ['git', '-C', source, 'rev-parse', 'HEAD'], capture_output=True, text=True, check=False,
).stdout.strip()
source_branch = subprocess.run(
    ['git', '-C', source, 'branch', '--show-current'], capture_output=True, text=True, check=False,
).stdout.strip()
dirty = subprocess.run(
    ['git', '-C', source, 'status', '--porcelain'], capture_output=True, text=True, check=False,
).stdout.strip().splitlines()
config = {
    'embedding_provider': os.getenv('EMBEDDING_PROVIDER', 'tfidf'),
    'embedding_model': os.getenv('EMBEDDING_MODEL', ''),
    'chroma_path': chroma,
    'rag_min_score': os.getenv('RAG_MIN_SCORE', '0.2'),
    'port': port,
}
manifest = {
    'source_path': source,
    'source_commit': source_commit,
    'source_branch': source_branch,
    'source_dirty_files': len(dirty),
    'target_path': target,
    'created_at': datetime.now(timezone.utc).isoformat(),
    'config': config,
    'config_hash': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
    'venv_python': sys.executable,
    'capabilities': {item['name']: item['state'] for item in probe_capabilities()},
    'worker': worker_status(),
    'workspace_count': Workspace.objects.count(),
    'notes': [
        'Do not expose this demo server to the public internet.',
        'Local preview uses the tfidf lexical baseline unless BGE was explicitly prepared.',
        'BGE, cross-encoder, live LLM, OCR/ASR, keyframes and Piston remain unverified/optional.',
    ],
}
Path('.deployment-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

preview = f"""# AlgoMentor 本地预览

- 实际路径：`{target}`
- 源仓库：`{source}`
- 源提交：`{source_commit}`（分支 `{source_branch}`，未提交文件 {len(dirty)} 个）
- 启动：`{target}/scripts/local_start.sh`
- 停止：`{target}/scripts/local_stop.sh`
- 状态：`{target}/scripts/local_status.sh`
- 诊断：`{'/Volumes/半岛铁盒/实验室/.venv/bin/python'} {target}/scripts/local_doctor.py`
- 默认地址：`http://127.0.0.1:{port}/workbench/`
- 日志：`{target}/data/run/server.log`、`{target}/data/run/worker.log`
- 数据：`{target}/data/db.sqlite3`；Chroma：`{chroma}`
- 演示凭据：仅保存在 `{target}/data/run/demo_credentials.txt`（若为新建账户）；既有账户密码不重置。

## 能力状态（探针实测）

{json.dumps(manifest['capabilities'], ensure_ascii=False, indent=2)}

## 边界

- 仅监听 `127.0.0.1`，不暴露公网。
- `tfidf` 是词法基线，不是 BGE 语义检索。
- 没有隔离执行服务时，代码分析只给静态证据与建议 diff，执行状态为 `UNVERIFIED`。
- 文献比较是上传文献的范围比较，不是系统综述。
"""
Path('LOCAL_PREVIEW.md').write_text(preview, encoding='utf-8')
print('manifest and LOCAL_PREVIEW.md written')
PY

echo "环境准备完成。启动：$DEPLOY_DIR/scripts/local_start.sh"
