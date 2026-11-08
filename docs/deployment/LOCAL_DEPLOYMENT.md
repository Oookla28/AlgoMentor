# 本地部署说明

## 2026-11-08 续建：Evidence 工作台本地预览

### 实际交付

- 源仓库：`/Volumes/半岛铁盒/实验室/AlgoMentor`
- 交付目录：`/Volumes/半岛铁盒/实验室考核部署`
- 实际地址：`http://127.0.0.1:8010/workbench/`
- 运行方式：Django `runserver 127.0.0.1:8010 --noreload --insecure` + `manage.py workbench_worker --poll 2`
- PID：`data/run/server.pid`、`data/run/worker.pid`；端口：`data/run/port.txt`
- 日志：`data/run/server.log`、`data/run/worker.log`
- 数据库：`data/db.sqlite3`；Chroma：`/tmp/algomentor-deploy-chroma`
- 数据库快照：`data/backups/<timestamp>/db.sqlite3`（SQLite backup API，不直接复制活跃主文件）

### 命令

```bash
# 首次安装或安全升级：保留 data/.env/既有索引，不重置密码
/Volumes/半岛铁盒/实验室考核部署/scripts/local_setup.sh

# 启动 Web + worker；端口占用时从 8020-8099 选择替代端口
/Volumes/半岛铁盒/实验室考核部署/scripts/local_start.sh

# 状态/诊断
/Volumes/半岛铁盒/实验室考核部署/scripts/local_status.sh
/Volumes/半岛铁盒/实验室/.venv/bin/python /Volumes/半岛铁盒/实验室考核部署/scripts/local_doctor.py

# 停止：只结束本项目记录且命令/工作目录匹配的 PID
/Volumes/半岛铁盒/实验室考核部署/scripts/local_stop.sh

# 回滚
ls /Volumes/半岛铁盒/实验室考核部署/data/backups/
# 停止服务后，用对应快照替换 data/db.sqlite3；代码回滚请使用独立 Git 工作树/备份，勿 reset --hard
```

### 环境与安全

- `.env` 不存在时才生成新的 `DJANGO_SECRET_KEY` 与 `APP_ENCRYPTION_KEY`；已存在时从不覆盖，避免既有 BYOK 密文失效。
- 默认 `EMBEDDING_PROVIDER=tfidf`、`RAG_MIN_SCORE=0.2`，明确是词法基线，不是 BGE。
- 只监听 `127.0.0.1`，不暴露公网/局域网。
- 演示账户：既有 `demo_student` / `demo_staff` 密码不重置；新建账户的随机密码只写入 `data/run/demo_credentials.txt`（0600）。
- 工作台 worker 未启动时任务保持 QUEUED，UI 会显示“任务服务未启动”；启动 worker 后自动继续。
- 代码分析不执行用户代码；没有隔离执行服务时状态为 `UNVERIFIED`。

### 验收证据

- 完整回归：`422 passed, 2 skipped`
- 工作台开发集：`tests/evaluation/workbench_results.json`
- 浏览器截图：`/Users/oookla/Downloads/workbench-1440.png`、`workbench-qa.png`、`workbench-paper.png`、`workbench-code.png`、`workbench-retry.png`、`workbench-390.png`、`workbench-768.png`、`workbench-1920.png`

### 已知阻塞

- BGE / Cross-Encoder / 在线 LLM / OCR / ASR / Piston 未验证；不得把词法结果写成 BGE 结论。
- 资料解析仍在上传请求内同步执行，大文件耗时较长。
- 工作台评测为 11 条手写开发集，不是大规模人工标注。


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
