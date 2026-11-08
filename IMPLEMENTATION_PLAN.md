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
| 测试 | `apps/knowledge/tests/test_*` | 完成 | 增量后 371 passed / 2 skipped（新增 51 项） |
| 评测脚本 | `scripts/evaluate_evidence_rag.py` | 完成 | TF-IDF 高级索引 advanced 9/9、库外拒答 2/2；legacy 6/9；结果 `tests/evaluation/evidence_rag_results.json` |
| 文档 | README / ARCHITECTURE / TESTING / DELIVERY_REPORT / baseline | 完成 | 与真实代码和验证结果同步 |

### 仍需外部资源的验证

1. 安装本地 BGE 权重后执行 `ingest_knowledge --advanced --rebuild`，比较 BGE 高级索引与 TF-IDF 基线；
2. 安装 `requirements-rag-multimodal.in` + tesseract/ffmpeg 后验证真实 OCR/ASR/关键帧；
3. 显式设置 `EVIDENCE_RAG_RERANK_BACKEND=cross_encoder` 后验证真实交叉编码器；
4. 在具备 `data/db.sqlite3`、BGE 与本机 Piston 的环境重新运行 `verify_offline.py`；
5. 使用个人 DeepSeek Key 进行生成契约与 claim 级引用的人工对照；这些项目前标记为 UNVERIFIED/OPTIONAL，不能冒充已完成。
