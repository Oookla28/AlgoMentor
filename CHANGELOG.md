# Changelog

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
