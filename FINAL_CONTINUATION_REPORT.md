# AlgoMentor V2 续建最终交付报告

生成日期：2026-11-08（Asia/Shanghai）

## 0. 2026-11-09 增量：导航与文献推荐

- 左侧导航新增“我的空间 / 文献库 / 代码分析”，工作台通过 `?view=spaces|literature|code` 切换。
- “我的空间”按私有/共享分组，明确每个账号的云空间独立。
- 文献库基于当前用户私有文献与内置离线目录做关键词推荐，显示推荐依据；不读取其他用户私有文献。
- 代码分析视图展示代码空间、执行边界与 `UNVERIFIED` 状态。
- 新增测试后完整回归 **426 passed / 2 skipped**。

## 1. 基线与最终提交

| 项目 | 值 |
| --- | --- |
| 续建前基线 | `1c927e0`，`main`，工作区干净，`398 passed / 2 skipped` |
| 本轮功能提交 | `b798c22`（私有 Evidence 工作台、任务运行、Skills、三领域 Demo） |
| 最终文档/评测提交 | `0b6683f`（其后仅可能有报告文字修订；以 `git log -1` 为准） |
| 最终完整回归 | **423 passed / 2 skipped**（源仓库；skip 为显式 live Piston / Wikimedia 集成） |
| 源仓库 | `/Volumes/半岛铁盒/实验室/AlgoMentor` |
| 交付目录 | `/Volumes/半岛铁盒/实验室考核部署`（无 `.git`，保留既有数据） |
| 部署地址 | `http://127.0.0.1:8010/workbench/` |
| 运行模式 | `runserver 127.0.0.1:8010 --noreload --insecure` + `workbench_worker --poll 2` |
| 数据 | `data/db.sqlite3`；Chroma `/tmp/algomentor-deploy-chroma`；SQLite 快照在 `data/backups/` |

未执行：`git push`、`git reset --hard`、`git clean -fd`、删除数据库、覆盖 `.env`、重建加密主密钥、伪造验收结果。

## 2. 复用与新增

### 复用（未重写）

- 旧搜索/聊天/Citation/`[来源N]`/课程/图谱/练习/报告/Wikipedia/离线路径。
- EvidenceRAG：层次切片、Parent/Child、Small2Big、BM25+稠密、RRF、确定性重排、证据门控、冲突检测、引用核验、管理员维护。
- 平台：DomainPack/TaskPack/ToolSpec、AgentRun/Step、Evidence/Claim/ConflictSet、能力探针、平台评测。
- SQLite、Django 模板、原生 JS/CSS/SVG、既有 Chroma collection、旧 650/80 切片。

### 新增

- `apps/workspace`：Workspace / 成员 / WorkspaceDocument / TaskArtifact / SkillActivation / TaskFeedback / WorkerHeartbeat。
- 工作台：空间切换、上传解析状态、失败重试、软移除/恢复、受控任务、真实阶段、引用定位、产物下载、草稿恢复、刷新恢复、取消/重试、反馈。
- 任务运行：QUEUED/RUNNING/WAITING_USER/SUCCEEDED/PARTIAL/FAILED/CANCELLED；worker 租约/心跳/过期重排/取消检查；预算与真实估算 usage。
- 领域/任务：`generic`、`research_literature`、`software_engineering` 新包；`grounded_qa`、`guided_learning`、`paper_comparison`、`code_investigation`。
- 6 个原生 Skill 与渐进式 Skill Runtime；开发 Skill 仅参考并记录为 `SOURCE_NOT_FETCHED`。
- 三领域演示资料、`seed_workbench_demo`、`evaluate_workbench`、11 条开发案例。
- 部署脚本 `local_setup/start/stop/status/doctor` 与 `.deployment-manifest.json` / `LOCAL_PREVIEW.md`。
- 全局字体统一宋体（用户要求），主题/布局未换肤。

## 3. 迁移与数据保护

新增迁移：

- `workspace.0001_initial`
- `platform.0002_agentrun_attempts_agentrun_cancel_requested_and_more`
- `platform.0003_agentrun_workspace_alter_agentrun_status`

升级前：

- 使用 SQLite backup API 生成一致性快照，不直接复制活跃主文件。
- 保留 `.env`、加密主密钥、既有用户、会话、索引与课程数据。
- 不重置既有 `demo_student` / `demo_staff` 密码；新建账户才生成随机密码到本机私有文件。

修复的数据一致性问题：

- 同一文件上传到不同空间时，片段 ID 使用目标文档加盐哈希，避免跨空间共享/偷走 chunk。
- TF-IDF 向量器首次拟合后复用，避免多文档维度漂移。
- 高级索引只校验本文档存在的 ID，不再错误要求整个共享 collection 数量等于当前文档片段数。

## 4. 普通用户操作

1. 登录后打开 `http://127.0.0.1:8010/workbench/`。
2. 选择工作空间；“新建空间”可创建私有空间并选择领域包。
3. 在“空间资料”上传文件；状态为“可检索”后即可提问。失败资料可重试/移除，已移除可恢复。
4. 选择任务类型与预算（快速/标准/深入），输入目标后提交。
5. 查看结果、`[来源N]` 引用、证据抽屉、阶段摘要；可取消、重试、反馈、下载产物。
6. 共享课程空间只读；普通用户看不到管理员平台入口。

## 5. 三个 Demo（已真实运行）

### A. 资料问答 / 引导学习

- 空间：`资料问答示例`（generic）
- 问题：`循环队列判满条件是什么？`
- 结果：`SUCCEEDED`，1 条证据，引用可跳到 `/knowledge/source/...`；浏览器上传 `learning_notes.md` 后状态“可检索”，新建私有空间成功。

### B. 文献比较

- 空间：`文献比较示例`（research_literature），3 篇文献
- 问题：`比较这些论文的方法与局限`
- 产物：`paper-comparison.md`（约 1.5 KB）与 `paper-comparison.html`（约 2.5 KB）；表格包含方法/实验条件/主要结论/局限，明确“不是系统综述”；缺失字段标注。

### C. 代码分析

- 空间：`代码分析示例`（software_engineering）
- 问题：`库存扣减的异常处理有什么问题？`
- 产物：`code-investigation.md`、`code-investigation.html`、`suggested.patch`（204 字节 unified diff）
- 发现：`inventory.py:22` None 比较、`:28` 过宽异常、`:29` 静默吞掉；执行状态 `UNVERIFIED`，建议 diff 未应用，未运行测试。

## 6. Skills 锁定与触发证据

- 原生 Skill：`grounded-knowledge-answering`、`guided-learning`、`evidence-paper-comparison`、`repository-investigation`、`experiment-review`、`task-recovery`。
- 运行证据：`TaskArtifact` 的 run 中 `SkillActivation` 记录了 skill_id/version/hash（研究视图）、触发来源、工具交集与结果摘要；工作台用户视图隐藏 hash/tool 细节。
- 权限：服务端计算 `TaskPack ∩ DomainPack ∩ Skill 声明 ∩ 已批准 ToolSpec ∩ 当前能力`；Skill 不能扩权。
- 开发 Skill：`skills.lock.json` 中 8 个候选均为 `REFERENCE_ONLY_NOT_INSTALLED` / `SOURCE_NOT_FETCHED`；本机 DNS 不可用，未下载、未安装、未伪造 commit/hash。

## 7. 真实测试与评测

### 自动化

- 完整回归：**423 passed / 2 skipped**。
- Django check：通过；`makemigrations --check`：无漂移。
- 新增测试：权限隔离、Skill 安全、任务取消/重试/租约、三领域产物、加盐切片 ID、私有原文访问控制、产物下载隔离。
- 真实 worker：`manage.py workbench_worker --once` 将 QUEUED 任务执行到 `SUCCEEDED`。

### 工作台开发集（部署环境，TF-IDF 词法基线）

| 指标 | 结果 |
| --- | --- |
| 案例 | 11（8 可答 / 3 不可答） |
| answerability accuracy | **1.0** |
| retrieval recall mean | **1.0** |
| MRR mean | **0.9375** |
| citation presence（可答） | **1.0** |
| unsupported claim rate mean | **0.0455** |
| latency p50 / p95 | **349 ms / 1863 ms** |
| failed cases | **0** |

原始逐例结果：`tests/evaluation/workbench_results.json`（含 git_sha `b798c22`、config hash、dataset hash、逐例 trace 与失败/限制说明）。

### 浏览器验收

- 1440：登录、工作台、创建私有空间、上传、问答、引用定位、文献比较下载、代码分析下载、刷新恢复、重试。
- 390 / 768 / 1920：无文档级横向溢出；提交按钮与任务列表可达；控制台 0 error。
- 共享空间普通用户只读；跨用户 API 403；私有原文页 403。

截图：

- `/Users/oookla/Downloads/workbench-1440.png`
- `/Users/oookla/Downloads/workbench-qa.png`
- `/Users/oookla/Downloads/workbench-paper.png`
- `/Users/oookla/Downloads/workbench-code.png`
- `/Users/oookla/Downloads/workbench-retry.png`
- `/Users/oookla/Downloads/workbench-390.png`
- `/Users/oookla/Downloads/workbench-768.png`
- `/Users/oookla/Downloads/workbench-1920.png`

## 8. 未验证与已知限制

- BGE、Cross-Encoder、在线 DeepSeek 生成、OCR/ASR、关键帧、Piston/Judge0：未验证/环境受限；不得把 TF-IDF 写成 BGE。
- 工作台评测是 11 条手写开发集，不是 120–180 条人工标注；不能作为泛化或学习效果结论。
- 文献比较只覆盖已上传正文，不是系统综述。
- 代码分析只读静态证据，不执行用户代码，执行状态固定 `UNVERIFIED`。
- 上传解析在请求内同步执行；大文件会延长请求时间。
- 生产多租户、公网安全、手机实机未验收；本地只监听 `127.0.0.1`。

## 9. 回滚

```bash
# 停止本项目进程（只结束命令与工作目录匹配的 PID）
/Volumes/半岛铁盒/实验室考核部署/scripts/local_stop.sh

# 数据库快照
ls /Volumes/半岛铁盒/实验室考核部署/data/backups/
# 选择升级前快照，停止服务后替换 data/db.sqlite3（保留原文件副本）

# 代码回滚：使用独立 Git 工作树或既有备份，不要 reset --hard 覆盖未推送实现
```

## 10. 复现命令

```bash
cd /Volumes/半岛铁盒/实验室/AlgoMentor
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py check
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py makemigrations --check --dry-run
/Volumes/半岛铁盒/实验室/.venv/bin/python -m pytest -q

cd /Volumes/半岛铁盒/实验室考核部署
scripts/local_status.sh
python scripts/local_doctor.py
scripts/healthcheck.sh
```
