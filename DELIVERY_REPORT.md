# 数构智学开发与验收报告

> 本文保留初始发布版本的验收记录。Wikipedia 与离线学习增量的最新功能、320 项回归和冷启动证据见 [增量开发报告](WIKIPEDIA_OFFLINE_REPORT.md)。

记录日期：2026-10-13（Asia/Shanghai）。完整源代码位于 AlgoMentor/。本报告区分已实现、本机测试和真实服务验证。本机隔离执行已接通；线上 AI 全档位、CrewAI 与完整安全审计仍不能宣称全部验收通过。

## 第一部分：项目完成情况

已建立可运行 Django Web 系统、账户注册登录、个人配置与加密 BYOK、真实课程入库、五个 LangChain 工具、隔离评测适配、题库、提交 / 错题 / 学习活动、规则指数与 BKT、动态知识网络、学习路径、五个 Python 算法演示、真 CrewAI 报告队列、异常映射、个人预算与测试实验脚本。

本机可独立使用知识库检索、原文追溯、知识图谱、算法演示及学习分析。本机学生代码现由独立 Lima VM 内的官方 Piston / Isolate 与 Python 3.12.0 执行，无需公共执行授权。生成类功能仍使用网页个人 Key。历史执行失败保留为无有效成绩。

## 第二部分：模块实现说明

- accounts：Django 认证、学习目标、Fernet/MultiFernet 密钥、网页保存/删除/真实连接测试、按用户 usage 和事务预算。
- knowledge：保存完整原始课程 PDF，LangChain 切分、BGE 中文本地向量、Chroma 持久化、文档哈希、512维与索引版本、原文页码和片段详情、教师审核勘误。
- agents / tutor：create_agent、DeepSeek BaseChatModel 适配、思考字段正确回传、时钟 / ORM / Wiki / Chroma / 执行工具、真实调用 Trace、教学状态与分级提示。
- problems / learning：21道原创练习与89个服务端用例；真实远程执行适配，幂等提交与原子学习闭环、隐藏用例不泄漏、真实诊断接口、错题重做与复习、掌握度/快照/推荐。
- graph：45个知识点、4章及课程根节点，54条先修/关联关系，NetworkX DAG 校验、稳定布局、聚合进度、历史恢复、SVG 搜索/缩放/拖动/点击/原文/路径。
- visualization：单链表反转、KMP、BF、循环队列、顺序栈。所有帧由 Python 决定，播放和前后步由原生 JS 渲染。
- reports：Researcher 与 Writer、两个 Task、Process.sequential、crew.kickoff；客观数字使用 SQLite 快照生成并核验；后台 Worker 持久化任务和强制超时。

## 第三部分：真实测试结果

|验证|实际结果|证据|
|---|---|---|
|pytest完整测试|218 passed, 1 skipped in 7.83s（跳过项另作真实执行）|data/pytest-final.log|
|Django系统检查|无问题|实际 manage.py check|
|生产配置部署检查|无警告|实际 check --deploy --settings=config.settings.production|
|迁移一致性|No changes detected|实际 makemigrations --check --dry-run|
|依赖兼容|No broken requirements found|实际 pip check|
|课程入库|15页、35块、512维BGE向量|KnowledgeDocument / Chroma索引|
|BGE检索实验|9个库内问题全部Hit@4，2个库外返回无证据；所有来源元数据可核对|tests/evaluation/results.json|
|可信自编参考程序|89个本地课程测试通过|apps/problems/tests/test_catalog.py；不接受学生代码|
|本机Piston真实执行|Python3.12.0打印与网页输入4输出10通过|tests/evaluation/local_execution.json；output/screenshots/local-python-execution.png|
|题库真实执行|21题、89用例全部ACCEPTED，不创建学生证据|tests/evaluation/problem_bank_results.json|
|提交接口真实闭环|独立测试数据库内实际运行/错题/重做/掌握/幂等/用户隔离，1 passed in 1.75s|data/pytest-live-execution.log|
|本机隔离探针|8 PASS、0 FAIL、1 UNVERIFIED；内存终止原因未独立证明|tests/evaluation/isolation_results.json|
|历史公共Piston探测|HTTP401，需授权；当前本机执行不使用它|tests/evaluation/execution_probe.json|
|Judge0公开服务|HTTP403|同上|
|六类真实判题实验|6/6匹配预期，agreement=1.0|tests/evaluation/judge_results.json|
|DeepSeek未认证探测|/models返回401；未验证推理|tests/evaluation/ai_external_probe.json|
|外部百科|中文红黑树摘要真实HTTP200、有效JSON|同上|
|浏览器桌面交互|登录空总览、图谱详情/先修路径、KMP逐步与BF比较、真实执行授权失败提示|output/screenshots与browser_qa.json|

LangChain 与 CrewAI 框架确实在测试中运行；付费 LLM 使用明确测试替身。常规单元测试的执行响应使用测试替身；另列的本机服务实验、题库与提交闭环确实使用真实 Piston。Worker超时测试实际运行可信测试子进程并确认终止。样本量小，不能将检索9/9推广为平台准确率。

## 第四部分：系统架构说明

采用 Django 模块化单体与 SQLite。账户、课程、教学、Agent、题目、学习、图谱、报告、实验分别管理自己的模型与服务；core 提供统一异常、JSON接口、LLM、加密和执行基础设施。外部 HTTP 放在数据库事务外，最终提交与学习状态使用 IMMEDIATE 事务和幂等约束。页面使用服务器模板和原生 SVG，无前端构建。

课程结构共享，进度/密钥/聊天/提交/错题/报告按当前认证用户独立查询。掌握度仅由统一服务写入，主页、图谱和报告读取同一状态。架构细节、公式与模型关系见 ARCHITECTURE.md。

## 第五部分：创新点与技术实现

- 可追溯的知识网络闭环：真实评测 → 原子提交 → 去重学习证据 → 掌握指数/BKT → 图谱/路径/错题/报告。
- 单题反复通过不会直接变成充分掌握；近期错误能导致可解释退步，章节聚合包括无证据节点。
- 原文与勘误分离；保留老师 PDF，待审核纠错不能作为正式课程证据。
- DeepSeek 思考工具消息保真，工具身份由服务器锁定，Trace 只记录真实执行和脱敏概要。
- CrewAI 分析与 Python 客观数字分离，数字快照不一致拒绝发布；任务超时可强制终止并持久化恢复。
- Python 确定性算法状态可逐步回放和BF/KMP比较，避免LLM编造动画过程。

## 第六部分：仍未解决的问题

1. 用户已在网页配置个人 DeepSeek Key，服务器日志可见真实聊天请求成功。三个档位、多工具线上任务、AI诊断、CrewAI在线报告与完整A/B/C质量实验未作系统性验收，不能从单次聊天成功推广。
2. 本机独立执行已完成：六类判题和全题库实际通过，禁网、主机文件/环境隔离、进程/输出限制、墙钟/CPU超时、临时文件隔离通过。200MiB分配在128MiB请求下被终止，但公共API没有OOM元数据，因此内存探针仍标UNVERIFIED；未做正式渗透测试。
3. 响应式CSS已实现，但浏览器视口工具实际仍保持1280×720，不能把本次桌面截图当手机测试；手机/平板实机验证待完成。
4. 当前检索测试集、题库和BKT先验规模有限。检索需更多人工核验问题，BKT默认参数未经拟合；未做正式渗透测试或实际生产反向代理部署验收。

## 第七部分：完整运行命令

本机虚拟环境、数据库、课程索引和隔离Python已经建立。重启电脑后先启动执行VM：

```bash
cd AlgoMentor
.venv/bin/python scripts/local_piston.py start
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

另开终端启动报告队列：

```bash
cd AlgoMentor
.venv/bin/python manage.py report_worker
```

新环境：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/bootstrap.py
.venv/bin/pytest -q
.venv/bin/python manage.py evaluate_system
```

网页注册并配置个人Key；执行服务部署见 deployment/LOCAL_EXECUTION.md。实测命令：

```bash
.venv/bin/python manage.py verify_problem_bank
.venv/bin/python manage.py verify_judge
.venv/bin/python manage.py verify_execution_isolation
ALGOMENTOR_LIVE_EXECUTION=1 .venv/bin/pytest -q tests/integration/test_live_execution.py
.venv/bin/python manage.py evaluate_system --live --username YOUR_USER
```

## 第八部分：现场演示流程

1. 新注册账户，展示个人总览无伪造成绩、知识点无学习证据。
2. 在课程知识库搜索“循环队列判满条件”，展开实际PDF页码与完整原文片段。
3. 搜索KMP图谱节点，点击名称，查看先修顺序、真实掌握指数、原文和相关练习入口。
4. 算法实验室选择KMP，逐步查看失配与next数组，使用同输入BF比较；链表查看prev/curr/next，循环队列查看队满和绕回。
5. 设置页面保存自己的DeepSeekKey，逐档进行真实推理测试，检查真实usage和错误状态。
6. 询问“查询我最近链表掌握情况，再执行代码并安排下一步”，核对实际工具调用Trace。需要合法执行服务。
7. 提交错误和正确程序，展示用例真实结果、错题保留、掌握度更新及图谱变化；查看不同用户隔离。
8. 启动report_worker，生成本周报告，展示任务状态、CrewAI研究员与写手逻辑，逐项核对数据库数字。
9. 如凭据缺失，当场展示真实配置/授权错误，并说明该线上环节待验证，不能表演伪造结果。

---

## 第九部分：EvidenceRAG Studio 增量交付记录（2026-11-08）

### 1. 交付范围与基线

| 项目 | 内容 |
| --- | --- |
| 上游快照 | `423b644` |
| 基线 HEAD | `e710827` |
| 功能分支 | `feat/evidence-rag-studio` |
| 基线测试 | 320 passed / 2 skipped |
| 增量后测试 | **398 passed / 2 skipped** |
| 系统检查 | `manage.py check` 无问题 |
| 迁移检查 | `makemigrations --check` 无变化 |
| 基线记录 | `docs/evidence_rag/baseline.md` |

增量不是重写：旧版 RAG、Citation、搜索 API、`[来源N]`、聊天时序、
知识图谱、代码评测、报告、Wikipedia 与离线学习都保留。所有新增
数据库字段可空或有默认值，旧数据无需回填。

### 2. 实际新增能力

| 能力 | 实现位置 | 交付状态 |
| --- | --- | --- |
| MIME 路由与多模态适配 | `mime_router.py`、`multimodal_loader.py`、`evidence_schema.py` | 完成；OCR/ASR/DOCX 可选后端未安装 |
| 结构感知递归切片 | `boundary_detector.py`、`hierarchical_chunker.py` | 完成；课程 PDF 实测 8 父块 / 29 子块 |
| 父块/子块层次 | `models.py`、`hierarchical_chunker.py` | 完成；迁移 `0004` |
| Small2Big | `small2big_service.py` | 完成；token budget + 父块/兄弟上下文 |
| BM25 稀疏检索 | `sparse_retrieval.py` | 完成；无外部服务依赖 |
| 独立高级 Chroma 索引 | `advanced_index_service.py` | 完成；TF-IDF 2048 维实测，BGE 高级索引 UNVERIFIED |
| 查询路由与改写 | `query_router.py`、`query_rewriter.py` | 完成；原始查询始终保留，LLM 改写默认关闭 |
| 多查询 + RRF | `hybrid_retrieval.py`、`rrf_service.py` | 完成；逐路轨迹落库 |
| 确定性重排 | `rerank_service.py` | 完成；交叉编码器 optional |
| 检索轨迹 | `trace_service.py`、`models.py` | 完成；查询级 + 逐路级 |
| 冲突检测与仲裁 | `claim_service.py`、`conflict_service.py` | 完成；规则后端 |
| claim 级引用核验 | `citation_verifier.py` | 完成；旧 `verified_citation_ids` 未改 |
| 管理 API | `views_evidence.py`、`config/urls.py` | 完成；staff + CSRF + 事务 |
| 片段树/轨迹/冲突/媒体 UI | `templates/knowledge/*`、`static/css/evidence-rag.css`、`static/js/knowledge.js` | 完成；浏览器实测 |
| 可选依赖说明 | `requirements-rag-multimodal.in` | 完成；核心依赖未加重型包 |
| 文档同步 | README / ARCHITECTURE / IMPLEMENTATION_PLAN / TESTING / 本报告 | 完成 |

### 3. 真实验证证据

1. **自动测试**：增量后 398 passed / 2 skipped；新增 78 项覆盖切片、
   Small2Big、稀疏/稠密/RRF/重排、改写、冲突、引用核验、多模态、
   CRUD/权限/CSRF 与高级入库命令。旧测试未删除、未修改断言。
2. **课程 PDF 入库**：15 页 → 旧版 35 片段；高级 8 父块 / 29 子块；
   TF-IDF 2048 维；高级 collection `ev-adv-3276aef3b4b6faa840345085`。
3. **高级检索**：查询“循环队列判满条件”返回 6 条证据、70 行逐路轨迹，
   dense 与 sparse 两路均出现；结果含父块、heading path、字符范围、
   Small2Big 上下文与 Evidence ID。
4. **离线检索评测**：`scripts/evaluate_evidence_rag.py` 在 TF-IDF 高级索引上
   得到 advanced 9/9 库内命中、2/2 库外拒答；同环境 legacy 为 6/9 与 2/2。
   结果写入 `tests/evaluation/evidence_rag_results.json`，只作为本机小样本，
   不宣称生产准确率。
5. **浏览器 QA**：真实 Chrome 中 `demo_staff` 登录后验证：
   - `/knowledge/` 显示“高级检索”和“管理员维护”；
   - 勾选高级检索后显示“高级检索模式”、6 张证据卡、查询变体、
     dense/sparse 轨迹表与 Small2Big 面板；
   - “切片树”显示 8 父块 / 29 子块；
   - “管理员维护”显示上传、重建索引、加载片段、编辑片段控件。
6. **权限**：普通学生页面不出现“管理员维护”；写接口返回 403；
   无 CSRF 的写请求返回 403；媒体文件仅登录用户可读，路径穿越返回 404。

### 4. 明确未验证项

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 真实 BGE 高级索引 | UNVERIFIED | 本机未下载 BGE 权重；高级链路用 TF-IDF 完成集成验证 |
| 交叉编码器重排 | OPTIONAL / UNVERIFIED | 默认确定性后端；缺模型时自动回退 |
| LLM 查询改写 | OPTIONAL / UNVERIFIED | 默认关闭；无 Key 时确定性改写 |
| 图片 OCR | OPTIONAL / UNVERIFIED | 未安装 pytesseract/tesseract；缺失路径有 warning |
| 视频 ASR/关键帧 | OPTIONAL / UNVERIFIED | 未安装 faster-whisper/ffmpeg；保留原文件与人工标注 |
| 离线冷启动验证 | ENVIRONMENT-LIMITED | 初始化后页面/静态/RAG/百科缓存通过；停在未部署的本机 Piston；BGE 权重未装 |
| DeepSeek 在线生成 | NOT_VERIFIED | 未使用个人付费 Key |

### 5. 复现命令

```bash
python manage.py check
python manage.py migrate
python manage.py ingest_knowledge
python manage.py ingest_knowledge --advanced
python manage.py runserver
pytest -q
python scripts/verify_environment.py
python scripts/verify_offline.py
```

高级检索 API：

```bash
curl -s 'http://127.0.0.1:8000/api/v1/knowledge/search/?q=循环队列判满条件&mode=advanced'
curl -s 'http://127.0.0.1:8000/api/v1/knowledge/tree/'
```

### 6. 交付约束核对

- 未修改 `templates/base.html` 与 `static/css/app.css`；
- 未引入 React/Vue/Node 构建链；
- 未覆盖旧 Chroma collection；
- 未删除/重命名旧模型字段；
- 未改变 `Citation` 旧字段与搜索 API 旧字段；
- 未把改写查询当事实；
- 未在页面显示 traceback、服务器路径或 API Key；
- 未删除任何原测试；
- 可选依赖缺失不会阻止 Django 启动或旧 PDF RAG。

---

## 第十部分：Evidence-Grounded Platform 增量交付（2026-11-08）

### 1. 新增契约与模型

- `apps/platform/contracts`：DomainPack、TaskPack、ToolSpec、EvidenceUnit、ClaimUnit；
- `apps/platform/domains`：`data_structures`、`general_documents` 两个领域包；
- `apps/platform/models.py`：AgentRun/Step、Evidence、Claim、ConflictSet、
  EvaluationCase/Run、Domain/Task/Tool 记录；
- 迁移 `apps/platform/migrations/0001_initial.py`。

### 2. 显式 Agent 与自适应路由

- 状态机：ROUTE → PLAN → RETRIEVE → EVIDENCE_GATE → RETRIEVE_MORE /
  CALL_TOOL → CONFLICT_CHECK → VERIFY → ANSWER/ABSTAIN → END；
- 预算：步骤、Token 估算、工具调用、延迟、retrieve-more 次数；
- 工具契约：权限、超时、成本、幂等、证据策略；
- 自适应动作：keyword/semantic/read child/parent/siblings/source page/
  conflicting versions；
- 只保存步骤摘要，不保存完整 chain-of-thought。

### 3. 实际验证

| 项目 | 结果 |
| --- | --- |
| 完整回归 | **398 passed / 2 skipped** |
| 平台案例 | 19 |
| legacy hit / advanced hit | 0.75 / **1.00** |
| parent recovery | **1.00** |
| 库外拒答 | legacy / advanced 均 **1.00** |
| claim coverage | 0.976 |
| unsupported claim rate | **0.00** |
| abstention precision / recall | **1.00 / 1.00** |
| 冲突识别 | **5 / 5** |
| 工具权限 / 超时 / 无效调用 | 均按预期 |
| avg steps / tool calls | 11.14 / 2.0 |
| p50 / p95 latency | 226 / 246 ms |

原始结果：`tests/evaluation/platform_results.json`。

### 4. 用户体验

- 学生端：原搜索/来源/聊天/评测不变；高级检索只显示来源卡片、拒答说明、
  冲突证据与可折叠上下文，不显示逐路轨迹/Token/模型调用；
- 管理员端：`/knowledge/` 的切片树、管理员维护、`/platform/` 控制台
  （Capability Health、领域包、工具契约、Agent 运行、步骤、证据、Claim、
  冲突、评测运行）；
- 学生访问 `/platform/` 为 403；写接口 staff + CSRF；API 限流。

### 5. 部署

- 目标：`/Volumes/半岛铁盒/实验室考核部署`；
- 脚本：`scripts/local_deploy.sh`、`run_local.sh`、`healthcheck.sh`、
  `evaluate_local.sh`；
- Chroma 默认 `/tmp/algomentor-deploy-chroma`（外接卷锁限制）；
- 详见 `docs/deployment/LOCAL_DEPLOYMENT.md` 与 `DEPLOYMENT_REPORT.md`。

### 6. 仍未验证

BGE/Cross-Encoder、LLM 在线生成、OCR/ASR/关键帧、本机 Piston、手机实机、
生产安全审计。不得把 TF-IDF 100% 写成 BGE 结论，不得把一次在线调用写成
泛化实验或学习效果。
