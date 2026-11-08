# 数构智学实施与验收状态

两份原始 PDF 已完整读取，副本与提取文本保存在 knowledge/。原始考核优先于增强设计。工程现已实现，下面按实际证据记录状态；**整体仍未达到全部线上功能验收**，原因是用户 BYOK 和隔离执行授权尚未提供。

|模块|任务与依赖|当前状态|验证结果 / 剩余问题|
|---|---|---|---|
|工程|Python 3.12、Django、SQLite、冻结依赖|本机通过|迁移成功；check / 生产 deploy check 无问题；pip check 无冲突|
|账户|注册登录、个人目标、Fernet Key、轮换与删除|实现且测试通过|当前用户隔离、CSRF、预算、错误映射测试通过|
|DeepSeek|三个精确档位、requests、真实 usage、思考工具适配|实现；线上待验证|官方模型及参数核查；无 Key 的真实 /models 401；不能冒充推理成功|
|知识库|PDF / LangChain / 本地 BGE / Chroma / 引用 / 勘误|真实入库与检索通过|15 页、35 块、512 维；9 个课程问题 Hit@4 9/9，2 个库外拒答；小样本需扩充|
|Agent|create_agent、五个工具、身份锁定、真实 Trace、循环与预算|框架测试通过；线上规划待验证|真实框架时钟和 ORM 调用通过；Wiki真实200；付费模型使用测试替身的结果不算线上验收|
|执行|Piston / Judge0、限制、七类判题状态|适配器实现；线上受阻|Piston执行401，Judge0公共地址403；六项真实判题均 UNVERIFIED|
|练习与学习|21题89例、幂等提交、事务、错题、真实提示、规则 / BKT|本地测试通过|可信自编参考程序89例通过；跨用户、并发去重、退步、历史恢复通过；学生真实远程执行仍待授权|
|AI诊断与教学|三模式、持久会话、分级提示、真实 DeepSeek 诊断|实现且契约测试通过|实际 AI 解释待个人 Key；不能修改判题结果|
|图谱|稳定知识节点、54关系、聚合、先修 DAG、历史、SVG|后端与桌面交互通过|节点搜索 / 点击 / 详情 / 原文 / 路径 / 缩放 / 章节聚焦可用|
|算法|链表、KMP、BF、循环队列、栈，Python状态|算法测试与桌面演示通过|实际匹配示例下标5，KMP12次 / BF16次比较，由 Python 生成|
|报告|真 CrewAI 双Agent、SQLite Worker、数值核验、超时|框架与状态测试通过；线上生成待验证|真实 kickoff 使用测试LLM；真实子进程超时终止通过；报告 Worker 可运行|
|页面|18模板、原生CSS/JS、空/有记录状态、安全Markdown|桌面验证通过|15空状态 +7有记录 HTTP200，测试数据回滚；移动响应式CSS已实现，视口工具未改变实际尺寸，手机实机待验|
|实验与交付|测试、原始数据、文档与源码包|已保存|183 passed，7.16秒；完整说明和8部分交付报告；线上实验不伪造指标|

下一次工作应以现有源代码与这些记录继续：网页配置个人 Key → 配置授权执行服务 → verify_problem_bank / verify_judge → evaluate_system --live → 人工核验生成事实 → 手机实机测试。不得删除已实现功能来绕过外部验证。

---

## Evidence 工作台续建状态（2026-11-08）

| 阶段 | 状态 | 交付 |
| --- | --- | --- |
| P0 盘点与保护 | Done | `docs/continuation/implementation_inventory.md`；SQLite 备份；源/目标 Git 与数据核对 |
| P1 用户体验 | Done | 工作台空间切换、上传、解析状态、提问、来源定位、阶段记录、草稿恢复 |
| P2 领域与任务 | Done | 五个 DomainPack；grounded_qa / guided_learning / paper_comparison / code_investigation |
| P3 Agent 运行 | Done | QUEUED→…→CANCELLED；worker、lease、重试、恢复、预算、产物 |
| P4 Skill 集成 | Done（开发 Skill 仅参考） | 6 个原生 Skill；`skills.lock.json` 标记 SOURCE_NOT_FETCHED；权限交集与安全测试 |
| P5 证据策略 | Done（复用既有） | Small2Big 用于比较任务；scope 过滤；主张/引用核验 |
| P6 三领域 Demo | Done | 资料问答、文献比较（Markdown/HTML）、代码分析（报告 + patch） |
| P7 科研评测 | Done（小样本） | 11 条开发集；`tests/evaluation/workbench_results.json` |
| P8 部署与 README | Done | `local_setup/start/stop/status/doctor`；实际 8010 部署；浏览器验收截图 |

## EvidenceRAG Studio 增量实施状态（2026-11-08）

| 模块 | 实现 | 状态 | 验证结果 / 剩余问题 |
| --- | --- | --- | --- |
| 基线审计 | `docs/evidence_rag/baseline.md` | 完成 | 320 passed / 2 skipped；check 与迁移检查通过；离线探针因环境缺 DB/BGE/Piston 记为 UNVERIFIED |
| 数据模型 | `KnowledgeDocument`/`KnowledgeChunk` 增字段；`MediaAsset`、`EvidenceClaim`、`KnowledgeQueryTrace`、`KnowledgeRetrievalTrace`、`KnowledgeConflict` | 完成 | 迁移 `0004`，旧数据可读；未删除/重命名旧字段 |
| 多模态加载 | `mime_router.py`、`multimodal_loader.py`、`evidence_schema.py` | 完成（可选后端未装） | TXT/Markdown/PDF/图片元数据/视频标注测试通过；DOCX/OCR/ASR 缺失依赖路径有明确错误码 |
| 结构感知切片 | `boundary_detector.py`、`hierarchical_chunker.py` | 完成 | 课程 PDF 实测 8 父块 / 29 子块；弱结构回退、代码/表格保护、overlap、page/char span 测试通过 |
| Small2Big | `small2big_service.py` | 完成 | 父块、命中子块、相邻兄弟、token budget、Evidence ID 测试通过 |
| 稀疏检索 | `sparse_retrieval.py` | 完成 | BM25 中文单字+二元组；相关/无关查询测试通过 |
| 稠密/高级索引 | `advanced_index_service.py` | 完成（TF-IDF 实测；BGE 未装权重） | 独立 `ev-adv-*` collection；TF-IDF 2048 维真实 Chroma 检索通过；BGE 高级索引 UNVERIFIED |
| 查询路由/改写 | `query_router.py`、`query_rewriter.py` | 完成 | 原始查询始终保留；代码/冲突意图扩展；无 Key 确定性回退；LLM 改写默认关闭 |
| 混合检索/RRF | `hybrid_retrieval.py`、`rrf_service.py` | 完成 | dense+sparse 多查询、RRF 去重与逐路轨迹测试通过 |
| 重排 | `rerank_service.py` | 完成 | 确定性重排测试通过；交叉编码器为 optional，失败回退 |
| 冲突治理 | `claim_service.py`、`conflict_service.py` | 完成 | 否定/数字/版本/年份冲突；UNRESOLVED 与 A_WINS/B_WINS 测试通过 |
| 引用核验 | `citation_verifier.py`、`retrieval_service.py` | 完成 | 越界、缺失、无支撑、矛盾 claim 测试通过；旧 `verified_citation_ids` 未改 |
| 轨迹与树 API | `trace_service.py`、`views_evidence.py`、`config/urls.py` | 完成 | tree/document/chunk/trace/conflict/media 接口与权限测试通过 |
| 片段 CRUD | `views_evidence.py` | 完成 | staff-only、CSRF、事务、软删除/恢复、索引补偿测试通过 |
| 前端增量 | `templates/knowledge/*`、`static/css/evidence-rag.css`、`static/js/knowledge.js` | 完成 | 浏览器 QA：高级搜索 6 条证据 + 轨迹；切片树 8/29；管理员维护控件；学生不可见管理入口 |
| 离线/降级 | `hybrid_retrieval.py`、`query_rewriter.py`、`advanced_index_service.py` | 完成 | 无高级索引回退 legacy、LLM 改写失败回退、重排失败回退均有测试 |
| 测试 | `apps/knowledge/tests/test_*` | 完成 | 增量后 398 passed / 2 skipped（新增 78 项） |
| 评测脚本 | `scripts/evaluate_evidence_rag.py` | 完成 | TF-IDF 高级索引 advanced 9/9、库外拒答 2/2；legacy 6/9；结果 `tests/evaluation/evidence_rag_results.json` |
| 文档 | README / ARCHITECTURE / TESTING / DELIVERY_REPORT / baseline | 完成 | 与真实代码和验证结果同步 |

### 仍需外部资源的验证

1. 安装本地 BGE 权重后执行 `ingest_knowledge --advanced --rebuild`，比较 BGE 高级索引与 TF-IDF 基线；
2. 安装 `requirements-rag-multimodal.in` + tesseract/ffmpeg 后验证真实 OCR/ASR/关键帧；
3. 显式设置 `EVIDENCE_RAG_RERANK_BACKEND=cross_encoder` 后验证真实交叉编码器；
4. 在具备 `data/db.sqlite3`、BGE 与本机 Piston 的环境重新运行 `verify_offline.py`；
5. 使用个人 DeepSeek Key 进行生成契约与 claim 级引用的人工对照；这些项目前标记为 UNVERIFIED/OPTIONAL，不能冒充已完成。

---

## Evidence-Grounded Platform 增量状态（2026-11-08）

| 模块 | 实现 | 状态 | 验证 |
| --- | --- | --- | --- |
| 平台契约 | `apps/platform/contracts`：DomainPack、TaskPack、ToolSpec、Evidence、Claim | 完成 | 单元测试 |
| 领域包 | `data_structures`、`general_documents` + registry | 完成 | 两领域 manifest/任务包测试 |
| 平台模型 | AgentRun/Step、Evidence、Claim、ConflictSet、EvaluationCase/Run、Domain/Task/Tool 记录 | 完成 | 迁移 `platform.0001` |
| 能力探针 | `capabilities.py`：available/fallback/disabled/environment-limited/unverified/not-configured | 完成 | 探针测试 + 控制台 |
| 显式状态机 | ROUTE→PLAN→RETRIEVE→GATE→RETRIEVE_MORE→CONFLICT_CHECK→VERIFY→ANSWER/ABSTAIN | 完成 | 状态序列、无证据、预算、冲突测试 |
| 自适应路由 | 7 类只读动作、utility、1–2 次 retrieve-more 上限 | 完成（权重未校准） | 路由测试 |
| 工具契约 | 权限、超时、预算成本、幂等、证据策略 | 完成 | 权限拒绝/超时/无效调用测试 |
| 平台 API/控制台 | `/api/v1/platform/*`、`/platform/`（staff-only） | 完成 | 权限、CSRF、限流、run 详情测试 |
| 评测协议 | 19 例、B0–B5 矩阵、三组指标 | 完成 | `scripts/evaluate_platform.py` |
| 本地部署 | `local_deploy.sh`、`run_local.sh`、`healthcheck.sh`、`evaluate_local.sh` | 完成 | 实际部署记录见 `DEPLOYMENT_REPORT.md` |
| 完整回归 | 398 passed / 2 skipped | 完成 | `TESTING.md` |

平台增量不改变旧搜索 API 的 legacy JSON 字段、排序、错误码与空结果语义；
新增字段只进入 advanced/platform payload。
