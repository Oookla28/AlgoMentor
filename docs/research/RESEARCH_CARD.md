# Research Card · EvidenceRAG Studio

## 2026-11-08 追加：工作台与 Skills 研究问题

- **H4（任务运行）**：显式 QUEUED→…→CANCELLED 状态机 + 租约/预算/取消，是否能在不重复副作用的情况下提高任务可恢复性与用户可见性？
- **H5（Skills）**：在相同任务、相同预算下，加载项目原生 Skill 是否提高跨领域任务完成质量与工具选择正确率，同时不增加越权或幻觉？
- **H6（领域迁移）**：同一核心 Agent 在 generic / research_literature / software_engineering 三个领域完成闭环，是否证明领域包可插拔而非三套硬编码页面？

当前可报告证据：三领域 11 例开发集 answerability 1.0、Recall 1.0、MRR 0.9375；Skill 激活与工具权限交集有自动化测试；但 Skills 的质量增益尚未做对照实验，不能宣称已证明。


## 1. 基本信息

| 项目 | 内容 |
| --- | --- |
| 标题 | 可插拔领域知识包的 Evidence-Grounded Agent：层次化切片、混合检索与冲突感知证据治理 |
| 类型 | 系统 / 检索增强生成 / 证据治理工程研究 |
| 当前版本 | main @ 9cabf27 + 平台化增量 |
| 数据 | 数据结构与算法课程 PDF（15 页）+ 19 个平台评测案例 |
| 状态 | 工程实现与小样本验证完成；BGE/BGE-reranker/在线生成未验证 |

## 2. 研究问题

- **H1（检索）**：结构感知递归切片、父/子层次、BM25 + 稠密多查询与 RRF，
  是否比单路稠密检索更稳定地恢复可引用证据？
- **H2（证据治理）**：显式 claim 抽取、冲突检测、权威/时效仲裁与 claim 级
  引用核验，能否降低无支撑回答与静默冲突？
- **H3（平台化）**：领域包、任务包、工具契约、证据路由与评测抽象后，
  核心 Agent 能否在不写领域分支的情况下支持第二领域？

## 3. 方法摘要

1. **结构感知递归字符切割**：标题/章节只决定边界优先级与 metadata；
   代码块、表格、公式作为不可切分保护区间；父块 1200–2000 tokens、
   子块 300–500 tokens、约 12% 重叠。
2. **Small2Big**：检索子块，返回父块、命中子块与相邻兄弟，按 token budget 截断。
3. **混合检索**：BM25 稀疏 + Chroma 稠密，多查询 Fan-out，RRF（k=60），
   确定性重排（RRF、词法、标题、权威、parser confidence、freshness、冗余惩罚）。
4. **证据门控**：多字词法覆盖或稠密语义支持；不足则继续检索或 abstain。
5. **冲突治理**：否定、数字、单位、版本、年份、高相似相反表述；
   权威性与时效性综合分；差距不足时 `UNRESOLVED`，并列展示。
6. **显式 Agent 状态机**：START→ROUTE→PLAN→RETRIEVE→EVIDENCE_GATE→
   RETRIEVE_MORE/CALL_TOOL→CONFLICT_CHECK→VERIFY→ANSWER/ABSTAIN→END；
   只存步骤摘要、决策、证据 ID 与指标，不存完整 chain-of-thought。
7. **可插拔领域包**：`data_structures` 与 `general_documents`；核心 Agent
   通过 registry 查找 pack/task/tool，不写 `if domain == ...` 分支。

## 4. 数据与案例

- 课程 PDF：15 页，旧版 650/80 切片 35 块；高级 8 父块 / 29 子块。
- 检索评测：9 个库内问题 + 2 个库外问题。
- 平台评测：19 例，含同页近邻（队空/队满）、误导条件、跨页 multi-hop、
  库外拒答、否定/数字/单位/版本/年份冲突。
- 合成冲突 claim 用于规则后端评测，不写入课程知识库。

## 5. 指标

- retrieval_hit：Hit@k、Recall@k、MRR、nDCG@k、parent recovery、refusal rate；
- answer_support：claim coverage、citation precision/recall、supported ratio、
  unsupported rate、contradiction rate、abstention precision/recall、Brier/ECE proxy；
- agent_quality：steps、tool calls、p50/p95 latency、invalid call rate、
  permission rejection、timeout、conflict detection。

## 6. 当前结果（TF-IDF，非 BGE）

| 指标 | 结果 |
| --- | --- |
| advanced 库内命中 | 9 / 9 |
| legacy 库内命中 | 6 / 9 |
| 库外拒答 | advanced 2 / 2；legacy 2 / 2 |
| 平台 advanced hit rate | 1.00 |
| 平台 legacy hit rate | 0.75 |
| parent recovery | 1.00 |
| claim coverage | 0.976 |
| unsupported claim rate | 0.00 |
| abstention precision / recall | 1.00 / 1.00 |
| 冲突识别 | 5 / 5 |
| 工具权限/超时/无效调用 | 均按预期 |
| p50 / p95 latency | 226 ms / 246 ms |

## 7. 有效性威胁

1. **规模小**：单一 15 页 PDF、19 个 case，不能外推到其他课程/领域。
2. **Embedding 不是 BGE**：TF-IDF 是词法基线；BGE 高级索引未安装权重。
3. **置信度未校准**：ECE/Brier 为 coverage-based proxy；
   `U(action)` 权重是工程默认值，未在验证集校准。
4. **冲突规则有限**：规则后端不是完整 NLI；语义相反但词面差异大的冲突可能漏检。
5. **抽取式回答**：平台 Agent 当前不使用 LLM 生成；结论受证据片段质量限制。
6. **单机 SQLite/Chroma**：外部卷文件锁限制；并发与大规模未验证。
7. **未做学习效果实验**：不能声称提升学生成绩或掌握度。

## 8. 伦理与安全

- 课程资料视为不可信输入，不执行其中指令；
- 工具只读、权限声明、超时与预算；写操作仅 staff + CSRF + 事务；
- 不保存完整 chain-of-thought、API Key、服务器路径或 traceback；
- 不自动下载大模型、不默认公网抓取、不无限代码执行；
- 演示账号只用于本机，不写入公网。

## 9. 复现

```bash
python manage.py check
python manage.py migrate
python manage.py ingest_knowledge --advanced
pytest -q
python scripts/evaluate_evidence_rag.py
python scripts/evaluate_platform.py
```

原始结果：`tests/evaluation/evidence_rag_results.json`、
`tests/evaluation/platform_results.json`。

## 10. 下一步

- 在具备本地 BGE/Cross-Encoder 的环境运行 B2–B5；
- 扩充跨课程/跨领域数据与 hard negatives；
- 校准证据门控与路由 utility；
- 真实 OCR/ASR/关键帧与时间戳引用；
- 合规的前后测/对照学习效果实验。
