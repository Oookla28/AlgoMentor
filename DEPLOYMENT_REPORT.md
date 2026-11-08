# 本地部署报告

- 源目录：`/Volumes/半岛铁盒/实验室/AlgoMentor`
- 部署目录：`/Volumes/半岛铁盒/实验室考核部署`
- 源提交：`c2a9c71f54a6874eeac18e0289525ada6d6c651f`（分支 `main`，未提交文件数 2）
- 创建时间：2026-11-08 20:32:14 CST
- 端口：`8010`
- Chroma：`/tmp/algomentor-deploy-chroma`
- 备份：`/Volumes/半岛铁盒/实验室考核部署.backup.20261108_203155`

## 已验证

- `manage.py check`
- `makemigrations --check --dry-run`
- `migrate --noinput`
- `seed_knowledge` / `seed_problems`
- `ingest_knowledge --advanced`（TF-IDF 2048 维）
- 演示账号（仅本机）：`demo_student` / `demo_staff`

## 启动与停止

```bash
bash scripts/run_local.sh
bash scripts/healthcheck.sh
kill "$(cat /Volumes/半岛铁盒/实验室考核部署/data/run/server.pid)"
```

## 回滚

```bash
mv "/Volumes/半岛铁盒/实验室考核部署" "/Volumes/半岛铁盒/实验室考核部署.failed"
mv "/Volumes/半岛铁盒/实验室考核部署.backup.20261108_203155" "/Volumes/半岛铁盒/实验室考核部署"
```

## 实际 HTTP 验证（2026-11-08）

- 服务：`http://127.0.0.1:8010/`，PID `36959`，日志 `data/run/server.log`；
- `healthcheck.sh`：login 200、static 200、未登录 knowledge 302、
  未登录 capability API 401，全部 PASS；
- `demo_staff` 登录成功；`/knowledge/` 200，显示管理员维护，`data-staff="1"`；
- 高级检索“循环队列判满条件”200，`mode=advanced`，6 条证据；
- `/api/v1/platform/capabilities/` 200；`/platform/` 200；
- Agent run 200，状态 `COMPLETED`，11 steps，13 evidence；
- `demo_student` 访问 `/platform/` 为 403；`/knowledge/` 200 且不显示管理员维护。

## 未验证

BGE 高级索引、Cross-Encoder、LLM 在线生成、OCR、ASR、关键帧、本机 Piston、手机实机、生产安全审计。
