# 工程架构与决策

## 模块边界

Django 模块化单体，SQLite 持久化用户状态，无 Node 工程、Redis、Celery 或微服务。页面层只解析请求和返回模板 / JSON；服务组织业务事务；领域算法独立于 HTTP；core 提供 LLM、加密、异常与隔离执行适配。

```mermaid
graph TD
    Templates[Django Templates / SVG] --> Views[Views / Forms / JSON API]
    Views --> Accounts[账户与 BYOK]
    Views --> Tutor[教学会话]
    Tutor --> Knowledge[PDF / LangChain 切分 / BGE / Chroma]
    Tutor --> Agent[LangChain create_agent]
    Agent --> Tools[时钟 / 课程检索 / 学生 ORM / Wiki / 隔离执行]
    Views --> Problems[练习提交与真实判题]
    Problems --> Learning[唯一掌握度服务 / 错题 / 活动 / 快照]
    Learning --> Graph[NetworkX 先修 DAG / 稳定 SVG 坐标]
    Learning --> Reports[SQLite 队列 / CrewAI 双 Agent]
    Accounts --> Infra[core: DeepSeek / Fernet / requests]
```

knowledge 管理 Course、Chapter、KnowledgePoint、KnowledgeRelation、Document、Chunk、Correction。problems 管理 Problem、ProblemKnowledgePoint、TestCase、Submission、TestResult、ExecutionRequest。learning 管理 LearningActivity、MistakeRecord、MasteryState、MasterySnapshot。tutor 管理 ChatSession、ChatMessage、TeachingSession。accounts 管理用户配置及个人请求预算。agents 管理 AgentTrace、ToolInvocation。reports 管理 ReportTask、LearningReport。

## RAG

PDF 按实际页码提取，LangChain RecursiveCharacterTextSplitter 按段落与中文标点切分，650 字符块、80 重叠。原文文档哈希和 Embedding 标识生成稳定索引版本；Chroma 使用 cosine，文件与向量维度不混合。元数据包括文件名、哈希、章节、节、页码、chunk ID、来源类型和版本。首次入库之外不重复向量化 PDF；BGE 模型与词向量缓存独立。

默认本地 BGE 中文语义 Embedding，revision 与维度记录在数据库中。tfidf 是可配置、显式标记的字符词法基线，不能冒充 BGE。基线阶段的小型检索实验不足以证明混合检索有额外收益，因此当时未加入 BM25/RRF；本次增量在独立 advanced 模式中加入这些路径，并逐查询保存每路贡献，legacy 路径保持不变。证据门槛以实际库内/库外查询校验，仍需要更多问题校准，不能视为完美语义边界。

课程问答先取得真实证据再交给 Agent，模型引用编号经过服务器核对，前端显示数据库中的片段。没有内联引用时检索片段以独立参考证据展示，不能被解释为模型已经正确引用。教师原文中的 BF 下标和三对角公式问题以待审核 Correction 保留，教师审核后才进入问答证据。原始 PDF 不变。

## Agent 与模型

LangChain 当前 create_agent API，模型通过独立 BaseChatModel 适配 DeepSeek requests。多轮工具调用保留 reasoning_content 于运行内消息状态，用户聊天与 Trace 不保存推理字段。五个 StructuredTool 通过 Pydantic 输入约束，身份从认证上下文闭包绑定，模型不能提供任意 student_id。

每次工具调用保存真实开始时间、状态、耗时、错误类型与脱敏输入长度。限制重复签名、工具次数、总任务 deadline 和模型预算。工具结果、检索 PDF 和外部网页都属于不可信参考数据，不具备授权能力。没有凭据时抛出明确错误，不返回伪造 Agent 回答。

ModelRegistry 集中定义三个运行档位，使用明确模型与思考参数；返回模型校验可识别官方版本别名，意外替换报错。LLMProvider、EmbeddingProvider、VectorStore、CodeExecutionProvider、ExternalKnowledgeProvider、MasteryEstimator、GraphLayoutProvider 对应各自实际可替换边界，使用 Protocol / dataclass。

## 判题与一致性

学生代码只能发送到隔离执行服务。Piston、Judge0 适配真实接口；Judge0 使用提交 token 轮询；requests 禁止重定向，读取响应有大小上限。标准判题服务端管理隐藏用例；浏览器只能获得隐藏用例的序号、状态与耗时，不能得到输入、预期输出、原始输出或 traceback。

先原子持久化 PENDING 与请求幂等键，释放事务后外部评测，再在 SQLite IMMEDIATE 事务中提交结果、写入去重活动、更新错题和掌握度快照。JUDGE_ERROR 不产生掌握证据。相同请求键不得被复用为不同题目或代码；重复响应不重复记分。

## 掌握度与 BKT

规则指数：`100 × (0.35 × 题目覆盖 + 0.40 × 近期加权正确率 + 0.15 × 独立完成 + 0.10 × 难度表现)`。最近窗口默认八次，权重随时间顺序增加。覆盖按不同通过题目计算，重复刷同一道题不能增加覆盖。单一题目最高 55；至少五份证据、三个不同题目才解除不足证据限制，缺少任一则指数最多 84。近期错误可使指数下降，提示次数来自保存的教学状态并可记录学生自报值。参数集中于 mastery_service。

BKT 采用初始、学习转移、猜对、失误四参数贝叶斯更新，工程先验未拟合；规则指数和 BKT 概率分别保存与标记，切换估计器不会把两个数字混为同一含义。教师应在更大数据集上校准先验。

图谱由共享稳定结构和当前用户进度组合。章/课程指数按全部子知识点难度权重聚合；无证据点贡献零值，单点通过不会令整章掌握。NetworkX 检查先修环，用拓扑排序生成目标的先修路径，related 与 prerequisite 严格分开。历史图读取真实 Snapshot，没有记录不合成历史。Python 产生链表反转、KMP、BF、循环队列和栈的状态；浏览器只负责动画渲染。

## CrewAI 与任务恢复

数据库统计先确定提交数、去重题目数、正确率、每日趋势、知识点与错题表现、快照变化。生成时读取保存的学生快照。真实 Researcher / Writer、两个 Task、Process.sequential、crew.kickoff()，独立 service。写手结构化 metrics 必须等于快照；分析文本不得引入未经核验的数值，客观 Markdown 表格由 Python 渲染。

ReportTask 保存 PENDING/RUNNING/SUCCESS/FAILED/TIMEOUT，Worker 原子领取；每任务在可终止子进程运行，达到期限强制终止。这是可信应用工作进程，不用于执行学生代码。任务超时后不能发布迟到结果；没有 Worker 时有队列过期路径。选择模型档位在入队时冻结，之后更改个人默认档位不改变已排队任务。

## 密钥与权限

Django 自带认证 / CSRF / 会话。个人 Key 使用 Fernet，加密主密钥来自 `.env`；MultiFernet 支持旧密钥解密与轮换。只显示最后四位掩码，不返回完整 Key，不写浏览器存储、不写日志与 Trace。服务器地址仅由管理员环境变量配置，学生不能改变。每日和每分钟预算通过数据库事务预留；usage 缺失时不把未知消耗当零。详情 API 都按当前用户过滤，认证失败返回统一 401。

## Wikipedia 与外部服务降级（增量）

现有 WikipediaProvider 委托唯一 wikipedia_service：官方 Action API 搜索、保守标题匹配、摘要/修订/来源校验，Cache Aside 写入 SQLite WikipediaCache。共享缓存只包含公开词条与规范化公共别名，不保存完整私人问题。默认有效期七天；失败保留旧内容，并在来源卡片标明缓存时间、过期状态、语言、修订与许可。

LangChain 保留 create_agent 及原工具，新增 search_wikipedia 注册名。明确来源请求、课程证据不足的安全公开概念通过 wrap_model_call 中间件调用真实注册工具，再将结果作为不可信证据交给模型；结果和 Trace 来自实际执行。当前 DeepSeek thinking 不支持强制 named tool_choice，因此该路由不改变模型或思考模式。百科来源与课程来源分开校验与展示，个人学习数据仍由原 ORM 工具取得。

ServiceAvailability 持久保存 DeepSeek、Wikipedia、执行服务各自状态。业务请求更新成功/失败，普通状态 GET 无外网探测。全局网络错误、个人授权/额度错误、具体模型错误分开存储；冷却后原子领取半开尝试，真实成功恢复。百科缓存命中不会虚构在线状态。CodeDraft 按用户和题目/实验区保存，不产生提交或掌握证据。

BGE 查询默认 local_files_only，prepare_embedding_model 负责显式下载；向量标识与维度没有变化。生产配置通过 WhiteNoise 提供 collectstatic 后的静态文件，原生页面无 CDN 运行依赖。离线冷启动脚本在新进程、一次性数据库副本和外网 socket/DNS 阻断下启动实际 WSGI，检查课程、图谱、算法、缓存与本地 Piston，不更改主机网络或真实学生记录。

## EvidenceRAG Studio（增量）

### 1. 模块与数据边界

增量仍然位于 `apps/knowledge` 内部，不引入新的 Django app 或前端框架：

| 层 | 文件 | 职责 |
| --- | --- | --- |
| 模型 | `models.py` + `migrations/0004_*` | 文档/片段元数据、MediaAsset、EvidenceClaim、QueryTrace、RetrievalTrace、Conflict |
| 解析 | `mime_router.py`、`multimodal_loader.py`、`evidence_schema.py` | MIME 路由、适配器、统一 EvidenceUnit |
| 切片 | `boundary_detector.py`、`hierarchical_chunker.py` | 标题/章节边界、递归字符切割、父块/子块、content_hash |
| 索引 | `advanced_index_service.py` | 独立 `latest_index_version`、`ev-adv-*` collection、重建/删除/Upsert |
| 检索 | `query_router.py`、`query_rewriter.py`、`sparse_retrieval.py`、`hybrid_retrieval.py`、`rrf_service.py`、`rerank_service.py`、`small2big_service.py` | 多查询 fan-out、BM25/Chroma、RRF、重排、上下文扩展 |
| 证据治理 | `claim_service.py`、`conflict_service.py`、`citation_verifier.py` | 主张抽取、冲突检测、权威性/时效性仲裁、claim 级核验 |
| 轨迹 | `trace_service.py` | 查询级与逐路召回级持久化 |
| API/页面 | `views.py`、`views_evidence.py`、`config/urls.py` | 兼容搜索、树、上传、CRUD、轨迹、冲突、媒体文件 |

新增字段全部 nullable/有默认值；旧迁移只读不改；旧数据不需要回填即可读取。

### 2. 结构感知递归切片

`boundary_detector` 识别 Markdown 标题、`第X章`、编号小节，并把
围栏代码块、表格、`$$` 公式标记为不可切分的保护区间。`hierarchical_chunker`
仍以递归字符分隔符为主算法：

1. 按页面拼接全文并记录 `page_ranges`；
2. 检测章节，将相邻小节合并到 1200–2000 token 的父块；
3. 在父块内用递归分隔符切成 300–500 token 子块，约 12% 重叠；
4. 代码块、表格、公式保持原子；超长保护块允许超过上限但不被拦腰截断；
5. 写入 `heading_path`、`char_start/end`、`token_count`、`overlap_*`、
   `parser_confidence`、`content_hash`、`parent_chunk_id`。

弱结构文档没有标题时回退到纯递归切割，`parser_confidence < 0.45`，
入库不会失败。前端允许管理员修正父子关系与片段内容。

### 3. 检索链路

`advanced_retrieve()` 的固定顺序：

1. Query Router：空/短/代词/代码/版本/媒体/冲突意图；
2. Query Rewrite：始终保留原始查询，生成 2–5 个召回变体；无 Key 或
   LLM 失败时使用确定性词表扩展，绝不把改写结果当事实；
3. Dense：对每个变体查询每个文档的 advanced collection，按
   `1 - distance` 记录原始分；
4. Sparse：进程内 BM25（CJK 单字 + 二元组 + 拉丁词），不依赖
   Elasticsearch/Redis；
5. RRF：`sum(1/(k+rank))`，按 chunk_id 去重，默认 `k=60`；
6. Rerank：RRF、词法覆盖、标题匹配、权威性、parser confidence、
   freshness 与冗余惩罚的确定性加权；交叉编码器为可选后端，
   加载失败自动回退；
7. Small2Big：命中 child → parent → 相邻兄弟，按 token budget 截断，
   保留命中 child、父块标题、字符范围与 Evidence ID；
8. 冲突：抽取主张，规则检测否定/数字/单位/版本/年份/立场冲突，
   按权威性与时效性给出 `A_WINS`、`B_WINS` 或 `UNRESOLVED`；
9. 轨迹：`KnowledgeQueryTrace` + `KnowledgeRetrievalTrace` 记录每个
   变体、召回器、rank、原始分、RRF、重排与是否选中。

### 4. 兼容与降级

- `retrieve_knowledge()` 内部仍是旧路径；advanced 通过
  `retrieve_knowledge_with_trace(mode='advanced')` 接入；
- 没有 advanced 索引时返回 legacy 结果并标记 `ADVANCED_INDEX_MISSING`；
- 稠密打开/查询失败时标记 `DENSE_RETRIEVAL_FAILED` 并回退；
- 交叉编码器失败标记 `CROSS_ENCODER_UNAVAILABLE`；
- LLM 改写失败标记具体错误码；
- 所有 fallback 都出现在 API 的 `fallback` 字段与页面的 warning 中，
  不静默伪装成高级结果。

### 5. 管理 API 与一致性

- 写接口全部要求登录 + CSRF；`PATCH/DELETE/restore/upload/reindex`
  额外要求 `is_staff`；
- `PATCH` 在事务内更新 DB；若已有高级索引，则先 Upsert 向量，
  失败时恢复旧文本并补偿旧向量，再回滚事务；
- `DELETE` 先删向量再软删除；向量删除失败则不改变 DB；
- `restore` 先恢复 DB 再 Upsert，失败则回退为删除状态；
- 上传先写入 `data/evidence_uploads/<uuid>/<原名>`，解析/索引失败时
  标记 `partial` 并返回可操作 warning；
- 媒体文件接口按登录用户校验，并把文件路径限制在 `BASE_DIR` 与
  上传目录内，防止路径穿越；
- 旧 `KnowledgeChunk` 删除逻辑只作用于 `chunk_type='legacy'`，
  重建旧索引不会误删高级父/子块。

### 6. 前端隔离

`templates/base.html` 与 `static/css/app.css` 未修改。新增
`static/css/evidence-rag.css` 全部使用 `.evidence-rag-*` 前缀与现有
CSS 变量；`knowledge.js` 只扩展 `/knowledge/` 页面，使用 `AM.node`
和 `textContent` 渲染，不解析不可信 HTML。高级检索开关默认关闭，
切片树/管理员维护为页签；学生不渲染管理员面板。所有动态文本来自
后端 JSON，错误只显示可理解的消息。

### 7. 失败模式与未验证项

| 场景 | 行为 |
| --- | --- |
| 可选 DOCX/OCR/ASR 依赖缺失 | 返回 `OPTIONAL_DEPENDENCY_MISSING` / `OCR_UNAVAILABLE` / `ASR_UNAVAILABLE`，Django 正常启动 |
| 视频/音频无 ffmpeg | 保留原文件与人工标注，记录 `FFMPEG_UNAVAILABLE` |
| 高级 collection 不存在 | 回退 legacy 检索并记录原因 |
| embedding identity 与索引不一致 | 跳过该文档并记录 `DOC_EMBEDDING_MISMATCH` |
| 检索无命中 | `evidence_sufficient=false`，不生成伪证据 |
| 冲突分数接近 | `UNRESOLVED`，A/B 并列展示 |

真实 BGE 高级索引、交叉编码器、LLM 改写、OCR/ASR 在本环境标记为
OPTIONAL/UNVERIFIED；对应回退路径有自动化测试。

## Evidence-Grounded Platform（增量）

### 1. 契约与领域包

`apps/platform` 是独立 Django app，不修改旧模型：

- `contracts/domain_pack.py`：DomainPack、TaskPack 数据契约；
- `contracts/tool_spec.py`：ToolSpec（权限、副作用、超时、预算成本、幂等、
  证据策略）与 ToolResult；
- `contracts/evidence.py`：EvidenceUnit、ClaimUnit；
- `domains/registry.py`：按 ID 查找 pack/task；核心 Agent 不写领域分支；
- `domains/data_structures.py`、`general_documents.py`：两个领域 manifest。

### 2. 持久化模型

`AgentRun`、`AgentStep`、`Evidence`、`Claim`、`ConflictSet`、
`EvaluationCase`、`EvaluationRun`，以及 DomainPack/TaskPack/ToolSpecRecord。
步骤只保存输入/输出摘要、决策、reason code、证据 ID、延迟、Token 估算与
失败码，不保存完整 chain-of-thought。

### 3. 显式状态机与预算

`apps/platform/agent/state_machine.py`：

```text
START → ROUTE → PLAN → RETRIEVE → EVIDENCE_GATE
→ RETRIEVE_MORE / CALL_TOOL / CONFLICT_CHECK → VERIFY
→ ANSWER / ABSTAIN → END
```

预算：步骤、Token（估算）、工具调用、总延迟、retrieve-more 次数。
超出预算强制 abstain；最多 2 次 retrieve-more，无无限循环。

### 4. 自适应证据路由

`adaptive_router.py` 的只读动作：keyword_search、semantic_search、
read_child、read_parent、read_siblings、read_source_page、
retrieve_conflicting_versions。确定性 utility：

```text
U(action) = expected_support - λ·token_cost - μ·latency - ν·tool_calls - η·risk
```

权重是工程默认值，`calibrated=False`；没有验证集校准，不得写成研究结论。
动作受工具权限、超时、预算与 gate 停止规则约束。

### 5. 能力探针与隔离

`capabilities.py` 区分 available / fallback / disabled / environment-limited /
unverified / not-configured；不下载模型、不调用付费 API、不实时请求 Wikipedia。
`/platform/` 控制台与 `/api/v1/platform/*` 仅管理员可见敏感状态；
学生端只保留搜索/来源/拒答体验，不显示内部轨迹、Token 或模型调用。

### 6. 部署边界

本地脚本使用显式路径变量、时间戳备份、不删除目标数据；Chroma 默认放在
`/tmp` 以避开外接卷 SQLite 文件锁；部署前执行 check、迁移、测试、
ingest 与能力探针；启动脚本输出 URL/PID/日志/停止/回滚命令。
