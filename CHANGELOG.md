# Changelog

## Unreleased · 2026-11-09 · 导航重组与文献推荐

### Added

- 左侧导航新增“我的空间 / 文献库 / 代码分析”，工作台按 `?view=` 切换视图。
- “我的空间”按私有空间与共享课程空间分组，突出“所有账号云空间独立”。
- 文献库：展示当前空间论文，基于关键词从当前用户的其他私有文献与内置离线目录推荐相关论文，显示推荐词、来源与未联网说明。
- `GET /api/v1/workbench/literature/recommendations/`：仅允许当前用户可读空间，不跨用户推荐。
- 代码分析视图：代码空间入口、只读边界与 `UNVERIFIED` 说明。
- 新建空间按钮支持预选领域（文献/代码/通用）。

### Verified

- 8 个上游开发参考 Skill 已固定版本内置到 `agent_skills/vendor/`，包含真实 commit、正文/许可证 SHA-256 与 `skills_audit` 审计；不参与产品运行时。
- 430 passed / 2 skipped；新增文献推荐、跨用户隔离、四个视图、侧栏入口与 Skill 内置校验测试。
- 推荐为本地关键词匹配；内置目录未联网抓取，不伪造外部检索结果。

## Unreleased · 2026-11-08 · Evidence 工作台续建

### Added

- 私有 `Workspace` / `WorkspaceMember` / `WorkspaceDocument` / `TaskArtifact` / `SkillActivation` / `TaskFeedback` / `WorkerHeartbeat`。
- `/workbench/` 工作台：空间切换、上传解析状态、重试/移除/恢复、有据问答、引导学习、文献比较、代码分析、引用定位、产物下载、刷新恢复。
- `AgentRun` 扩展 QUEUED/RUNNING/SUCCEEDED/PARTIAL/CANCELLED、workspace、task type、stage、attempts、lease、cancel flag。
- `workbench_worker` 管理命令：租约领取、过期重排、取消、真实 usage/预算。
- 6 个原生 Skill 与渐进式 Skill Runtime；开发 Skill `skills.lock.json` / `THIRD_PARTY_NOTICES.md`。
- 三领域 Demo 资料与 `seed_workbench_demo`；11 条工作台开发集与 `evaluate_workbench`。
- `scripts/local_setup.sh`、`local_start.sh`、`local_stop.sh`、`local_status.sh`、`local_doctor.py`。

### Changed

- 全局字体按用户要求统一为宋体优先栈；主题、布局未换肤。
- `base.html` 增加“Evidence 工作台”入口。
- 文献比较使用 Small2Big 读取父块，并从 Markdown 标题提取方法/实验/结论/局限字段。
- 代码调查在识别到代码意图时对本空间做有界只读扫描；无代码意图的越界问题会拒答。
- `TfidfEmbeddings` 首次拟合后复用，避免多文档维度漂移；高级索引只校验本文档 ID，不再要求整个共享 collection 数量相等。
- 切片 ID 使用目标文档哈希，修复同一文件跨空间上传时的片段归属冲突。

### Fixed

- 私有原文页越权、任务/产物跨用户访问、跨空间同名文件共享 chunk ID。
- 任务列表阶段不刷新、inline `[来源N]` 不可点击、任务类型选项重复。

### Verified

- 422 passed / 2 skipped；真实 worker；真实浏览器 1440/390/768/1920；工作台 11 例开发集 answerability 1.0、Recall 1.0、MRR 0.9375。
- 仍未验证：BGE、Cross-Encoder、在线 LLM、OCR/ASR、Piston、生产多租户安全。

## Unreleased · 2026-11-08 · EvidenceRAG Studio + 平台化增量

### Added

- 结构感知递归字符切片、父/子块、Small2Big、代码/表格/公式保护。
- BM25 稀疏检索、稠密检索、多查询 Fan-out、RRF、确定性重排、证据门控。
- Query Router、确定性查询改写、可选 LLM 改写回退。
- 检索轨迹、媒体证据、冲突检测/仲裁、claim 级引用核验。
- 管理员上传、重建索引、片段编辑/软删除/恢复 API 与 UI。
- `apps/platform`：DomainPack、TaskPack、ToolSpec、AgentRun/Step、Evidence、
  Claim、ConflictSet、EvaluationCase/Run。
- 显式 Agent 状态机（ROUTE→PLAN→RETRIEVE→GATE→RETRIEVE_MORE→CONFLICT_CHECK
  →VERIFY→ANSWER/ABSTAIN），含步骤/Token/工具/延迟预算。
- 自适应证据路由（keyword/semantic/read child/parent/siblings/source page/
  conflicting versions），确定性 utility 与 1–2 次 retrieve-more 上限。
- 能力健康探针（available / fallback / disabled / environment-limited /
  unverified / not-configured）与管理控制台 `/platform/`。
- 平台评测协议、19 例数据集、检索/证据/Agent 指标与 B0–B5 矩阵。
- 本地部署脚本、healthcheck、evaluate_local、manifest 与回滚说明。
- `docs/research/RESEARCH_CARD.md`、`docs/evidence_rag/evaluation_protocol.md`、
  `docs/deployment/LOCAL_DEPLOYMENT.md`、`docs/evidence_rag/baseline_before_next_stage.md`。

### Changed

- Legacy 搜索 JSON 严格保持原 11 个 Citation 字段；高级字段只进入 advanced payload。
- `ingest_knowledge --advanced` 同时建旧版与高级索引；legacy rebuild 只清理 legacy chunks。
- `CHROMA_PATH` 可通过环境变量覆盖。
- 冲突检测增加 subject 相似度门槛、近似重复 claim 去重、代码片段过滤。
- 平台 Agent 回答改为抽取式证据 span；引用核验按最佳匹配句判断矛盾。

### Fixed

- 修复旧索引 rebuild 时未删除旧 collection 导致的重复 ID 风险。
- 修复删除片段时向量/数据库补偿路径。
- 修复 legacy 搜索泄漏高级 Citation 字段的兼容性问题。
- 修复外接卷 Chroma 不可写时的部署路径选择（默认 `/tmp`）。

### Verified

- 完整回归：见 `TESTING.md`（最终以实际运行数为准）。
- `scripts/evaluate_evidence_rag.py`：advanced 9/9、拒答 2/2；legacy 6/9。
- `scripts/evaluate_platform.py`：19 例，advanced 100%、legacy 75%、
  冲突 5/5、拒答 1.0/1.0、unsupported claim 0。
- 工具权限拒绝、超时、无效调用探针全部按预期。
- 真实浏览器：高级检索、切片树、管理员维护、平台控制台、无 JS 错误。

### Known limitations / Unverified

- BGE 高级索引、Cross-Encoder、LLM 在线生成、OCR、ASR、关键帧、
  本机 Piston、手机实机、生产安全审计未验证。
- 评测规模小；置信度为 proxy，不是校准概率；不得写成泛化或学习效果结论。
