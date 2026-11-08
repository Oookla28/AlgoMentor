# 测试说明

所有结果以 `data/pytest-final.log`、`tests/evaluation/results.json` 和外部服务探测原始 JSON 为准。执行命令见 README。

自动化层：pytest + pytest-django 隔离数据库。测试替身只在 tests 中注入，用于可重复验证请求参数、判题分类、状态转换、工具规划控制及错误处理。真实 LangChain create_agent 执行时间和 ORM 工具；真实 CrewAI kickoff 依次运行研究员和写手。付费模型的替身不能被解释为真实 DeepSeek 线上验证。Worker 超时测试实际启动可信测试子进程并确认终止；不是学生代码运行测试。

学习闭环检查 Accepted / Wrong Answer / Syntax Error / Runtime Error / TLE / MLE / Judge Error、隐藏数据保密、事务幂等、错题保留与重做解决、掌握度增长及回退、单题上限、无证据灰色图谱、章加权聚合、先修环拒绝与拓扑路径、真实快照及多用户隔离。

检索实验使用本机真实中文 BGE 和 Chroma；9 个库内问题来自已读 PDF，2 个库外问题检查拒答。原始每题命中、引用元数据、耗时均落盘。小样本结果只反映本组测试，不能推广成生产准确率。A/B/C 在线生成及事实一致性实验需要真实 Key，并保留回答供人工对照；未执行的指标标为 NOT_VERIFIED / REQUIRES_HUMAN_REVIEW。

Piston 运行列表读取成功不等于执行成功。本机现已部署独立 Lima VM 中的官方 Piston / Isolate 与 Python 3.12.0：六类实际判题全部匹配预期，21 道参考程序的 89 个用例实际通过。证据为 judge_results.json 和 problem_bank_results.json。verify_execution_isolation 另验证固定恶意行为探针并保留原始响应；含糊结果为 UNVERIFIED。历史公共实例 401/403 探测仍保留，但不代表本机当前服务状态。

页面验证以浏览器实际状态和日志保存：注册 / 登录、真实空总览、图谱搜索聚焦及节点详情、知识检索与来源、Python 状态演示、代码服务授权错误、未配置 Key 提示、响应式布局。浏览器 QA 使用的初始临时账户已经清理；当前使用既有登录态只验证“运行代码”，输入 4 实际输出 10，未创建测试学生成绩。已有正式账户与学习记录保留。

本次完整自动测试：218 passed、1 skipped；跳过项显式执行 `ALGOMENTOR_LIVE_EXECUTION=1 .venv/bin/pytest -q tests/integration/test_live_execution.py` 后 1 passed。该实测只写 pytest 测试数据库，验证真实 API 运行/提交、错题重做、学习证据、幂等和用户隔离，不污染正式学生记录。隔离探针本次 8 PASS、0 FAIL、1 UNVERIFIED：内存分配被终止，返回峰值约128MiB，但API未给OOM标记，保留未验证；网络/文件/环境/进程/输出/墙钟/CPU/临时文件检查均有实际证据。

## Wikipedia 与离线增量验收

本轮基线218通过、1跳过；最终320通过、2默认跳过。两个真实集成分别单独执行通过：真实LangChain+官方Wikipedia（规划LLM明确为测试替身）与真实Piston提交闭环。用户要求的四个概念实际API全部通过，额外合计6项；18项预热词表实际核对通过。离线冷启动在新WSGI进程、一次性数据库副本、外部DNS/socket与主机代理阻断下通过，DEBUG=False静态、BGE/Chroma、课程/图谱/算法、真实百科缓存和本机执行均可用。既有学生行指纹未变。完整证据与命令见 WIKIPEDIA_OFFLINE_REPORT.md 和 tests/evaluation/wikipedia_incremental_tests.json。未调用用户付费DeepSeek。

---

## EvidenceRAG Studio 增量测试（2026-11-08）

### 1. 数量与命令

| 阶段 | 命令 | 结果 |
| --- | --- | --- |
| 增量前基线 | `pytest -q` | 320 passed，2 skipped，52.84s |
| 增量后 | `pytest -q` | **398 passed，2 skipped** |
| 系统检查 | `python manage.py check` | 无问题 |
| 迁移检查 | `python manage.py makemigrations --check` | No changes detected |
| 环境检查 | `python scripts/verify_environment.py` | 通过 |
| 离线探针 | `python scripts/verify_offline.py` | 环境受限：初始化后页面/静态/RAG/百科缓存通过，停在未部署的本机 Piston；默认 BGE 权重亦未安装 |
| 检索评测 | `python scripts/evaluate_evidence_rag.py` | PASSED：TF-IDF 高级索引 advanced 9/9、库外拒答 2/2；legacy 6/9、拒答 2/2 |

新增 78 项测试位于：

- `apps/knowledge/tests/test_hierarchical_chunker.py`：标题、递归边界、弱结构、
  overlap、代码/表格保护、content_hash、page/char span、旧分片兼容；
- `test_small2big.py`：父块/命中子块/兄弟、token budget、旧 Citation 字段；
- `test_retrieval_advanced.py`：RRF、BM25、改写、确定性重排、TF-IDF + 真实
  Chroma 高级检索、无索引回退、legacy wrapper；
- `test_citation_verifier.py`：合法/越界/缺失/无支撑/矛盾 claim；
- `test_conflict_service.py`：否定/数字/版本/年份、UNRESOLVED、A_WINS、
  存储与序列化；
- `test_multimodal_loader.py`：TXT/Markdown/图片/视频、缺失 OCR/ASR/ffmpeg、
  不支持 MIME、空文件、EvidenceUnit；
- `test_evidence_api.py`：树/详情、学生只读、staff CRUD、CSRF、上传限制、
  轨迹权限、媒体文件路径穿越、管理员入口可见性；
- `test_advanced_ingestion.py`：`ingest_knowledge --advanced` 同时建旧版与
  高级索引、旧版 rebuild 不删除高级父/子块、Markdown advanced-only。

评测脚本 `scripts/evaluate_evidence_rag.py` 读取
`tests/evaluation/rag_cases.json`，对 9 个库内问题和 2 个库外问题分别运行
legacy 与 advanced，写入 `tests/evaluation/evidence_rag_results.json`。
脚本不调用 LLM 或外网；没有高级索引时返回
`SKIPPED_NO_ADVANCED_INDEX`，不伪造指标。

### 2. 离线与替身原则

新增测试默认：

- 不调用真实 DeepSeek；
- 不调用真实 Wikipedia；
- 不自动下载模型；
- 不访问外网；
- 不依赖 Docker/GPU；
- 使用 TF-IDF fake/deterministic embedding、临时 SQLite、临时 Chroma、
  `tmp_path` 文件与显式 warning 断言。

### 3. 实测数据

| 项目 | 结果 |
| --- | --- |
| 课程 PDF 结构感知切片 | 15 页 → 8 个父块 / 29 个子块 |
| 父块 token 分布 | 971 / 1900 / 平均 1297（目标 1200–2000，尾部受章节边界限制） |
| 子块 token 分布 | 100–511，平均 388（目标 300–500，短尾块与原子块例外） |
| 子块重叠 | 约 60 tokens / 块（约 12%，受保护块边界时不重叠） |
| 高级索引（本机） | TF-IDF 2048 维，`ev-adv-3276aef3b4b6faa840345085` |
| 高级检索示例 | “循环队列判满条件” → 6 条证据，70 行逐路轨迹，dense+sparse 双路 |
| 浏览器 QA | 高级检索、切片树、管理员维护、学生不可见管理入口 |
| BGE 高级索引 | UNVERIFIED（未安装本地权重） |
| OCR/ASR/关键帧/交叉编码器/LLM 改写 | OPTIONAL / UNVERIFIED（默认关闭，回退路径已测） |

### 4. 结果解释

- 398 passed 是本次环境实际运行结果；2 skipped 仍是原有的真实 Piston 与
  Wikimedia 在线集成，未删除、未改写。
- 高级检索的 TF-IDF 实测只证明链路可运行与可解释，不证明 BGE 语义质量；
  BGE 高级索引需要在有本地权重环境重新执行并比较。
- 冲突检测是轻量规则后端，不是完整 NLI；测试只覆盖规则可识别的模式。
- 浏览器 QA 在真实 Chrome 中完成，但窗口曾处于最小化状态；对首屏下方控件
  使用 DOM 存在性、尺寸、启用状态与文案取证，未做像素级截图。

## Evidence-Grounded Platform 增量（2026-11-08）

### 1. 新增测试

`apps/platform/tests/` 共 27 项：

- `test_contracts_and_capabilities.py`：两个领域包、任务包、工具契约、
  capability 状态词汇、manifest 同步；
- `test_adaptive_router.py`：无证据停止、门控满足停止、动作选择、成本惩罚；
- `test_metrics.py`：Recall@k、MRR、nDCG、citation precision/recall、
  abstention、Brier/ECE、percentile；
- `test_tool_registry.py`：写权限拒绝、超时、无效工具、真实关键词/
  父块/兄弟/原文页读取；
- `test_agent_state_machine.py`：完整状态序列、无证据拒答、预算拒答、
  冲突集合持久化、步骤摘要不存完整思维链；
- `test_platform_api.py`：capability API staff-only、控制台隔离、
  Agent run API、领域校验、限流、CSRF、run 详情 owner/staff。

### 2. 完整回归

- **398 passed, 2 skipped**（2026-11-08，15.24s）；
- 2 skip 仍为真实 Piston 与 Wikimedia 在线集成；
- `manage.py check`、`makemigrations --check` 通过。

### 3. 平台评测（TF-IDF）

`python scripts/evaluate_platform.py`：

- 19 例；advanced hit 100%，legacy hit 75%；
- parent recovery 100%；
- 库外拒答 legacy/advanced 均 100%；
- claim coverage 0.976，unsupported claim rate 0；
- abstention precision/recall 1.0/1.0；
- 冲突 5/5；
- 工具权限拒绝、超时、无效调用探针全部按预期；
- avg steps 11.14、avg tool calls 2.0、p50/p95 226/246 ms。

### 4. 未验证

BGE、Cross-Encoder、LLM 在线生成、OCR、ASR、关键帧、本机 Piston、
手机实机、生产安全审计。相关矩阵项见
`docs/evidence_rag/evaluation_protocol.md`。
