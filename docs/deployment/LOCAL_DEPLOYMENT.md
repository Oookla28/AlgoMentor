# 本地部署说明

## 1. 目标与路径

| 项目 | 默认值 |
| --- | --- |
| 源目录 | `/Volumes/半岛铁盒/实验室/AlgoMentor` |
| 部署目录 | `/Volumes/半岛铁盒/实验室考核部署` |
| 端口 | `8010` |
| 演示账号 | 部署脚本创建并打印（仅本机） |
| Chroma | 默认 `/tmp/algomentor-deploy-chroma`（避免外接卷 SQLite 锁问题） |

## 2. 前提

- Python 3.12 可用；已有项目 `.venv` 或通过 `VENV_PYTHON` 指定；
- 不自动下载 BGE/LLM/OCR/ASR 模型；
- 不暴露公网，只绑定 `127.0.0.1`；
- 目标目录存在时，部署脚本先创建时间戳备份，不执行 `rm -rf`，不覆盖
  `data/db.sqlite3` 与 `data/evidence_uploads`。

## 3. 脚本

```bash
bash scripts/local_deploy.sh
bash scripts/run_local.sh
bash scripts/healthcheck.sh
bash scripts/evaluate_local.sh
```

### local_deploy.sh

- 记录 source path、source commit、target path、created_at、config hash；
- rsync 源码（排除 `.git`、`.venv`、`data`、`__pycache__`、`._*`、`output`）；
- 保留目标已有 `data/`；
- 执行 `manage.py check`、`makemigrations --check`、`migrate`；
- 初始化课程知识库与题库；
- 使用 TF-IDF 建旧版 + 高级索引（不下载大模型）；
- 创建本机演示账号（可用 `DEMO_USERS=false` 关闭）；
- 写 `.deployment-manifest.json` 与 `DEPLOYMENT_REPORT.md`。

### run_local.sh

输出并写入 `data/run/`：

- 实际 URL、端口、PID、日志路径、health URL、停止命令、回滚命令；
- 使用 `nohup` 后台启动，`--noreload`；
- `EMBEDDING_PROVIDER=tfidf`、`RAG_MIN_SCORE=0.2`。

停止：

```bash
kill "$(cat /Volumes/半岛铁盒/实验室考核部署/data/run/server.pid)"
```

### healthcheck.sh

检查：

- `GET /accounts/login/` 200；
- `GET /static/css/app.css` 200；
- `GET /api/v1/platform/capabilities/` 未登录返回 401/403；
- 输出 PASS/FAIL，不访问外网。

### evaluate_local.sh

运行两个离线评测脚本，结果写入部署目录的
`tests/evaluation/evidence_rag_results.json` 与 `platform_results.json`。

## 4. 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SOURCE_DIR` | `/Volumes/半岛铁盒/实验室/AlgoMentor` | 源仓库 |
| `DEPLOY_DIR` | `/Volumes/半岛铁盒/实验室考核部署` | 目标目录 |
| `VENV_PYTHON` | `/Volumes/半岛铁盒/实验室/.venv/bin/python` | 运行 Python |
| `DEPLOY_PORT` | `8010` | 本地端口 |
| `CHROMA_PATH` | `/tmp/algomentor-deploy-chroma` | 向量库路径 |
| `DEMO_USERS` | `true` | 是否创建本机演示账号 |
| `DEMO_PASSWORD` | `demo-pass-2026` | 仅本机演示；生产禁用 |

## 5. 回滚

部署脚本在目标目录存在时生成：

```bash
/Volumes/半岛铁盒/实验室考核部署.backup.<timestamp>
```

回滚命令会写入 `data/run/ROLLBACK.txt`，例如：

```bash
mv "/Volumes/半岛铁盒/实验室考核部署" "/Volumes/半岛铁盒/实验室考核部署.failed"
mv "/Volumes/半岛铁盒/实验室考核部署.backup.20261108_xxxxxx" "/Volumes/半岛铁盒/实验室考核部署"
```

不删除失败目录，便于排查。

## 6. 已知限制

- 外接卷 Chroma 可能只读/锁失败；默认使用 `/tmp`，重启机器后需重建索引；
- 未部署本机 Piston，代码评测真实执行仍为 Environment-limited；
- 未安装 BGE/Cross-Encoder/OCR/ASR，相关能力显示为 Unverified/Disabled；
- 演示账号与固定密码只用于本机验收，不得用于公网。
