# 数构智学 · AlgoMentor

<p align="center"><strong>可插拔领域知识包的 Evidence-Grounded Agent 学习工作台</strong></p>

AlgoMentor 是一个面向真实知识任务的 Evidence-Grounded Agent 系统：它把课程学习、私有资料空间、结构感知检索、证据门控、可核验引用、任务运行与可下载产物整合在一个 Django 应用中。

系统既保留成熟的课程学习场景，也提供三个可直接体验的跨领域工作流：

- **资料问答 / 引导学习**：上传自己的笔记或课程资料，获得带原文出处的回答与学习提纲。
- **文献比较**：对多篇论文生成方法、实验条件、结论与局限的带引用对照报告。
- **代码分析**：在只读边界内定位代码证据，输出风险、建议 diff 与执行状态。

## 项目亮点

- **在普通 RAG 之上增加显式证据链**：检索、证据门控、主张抽取、引用核验、冲突检测和拒答都是可检查的链路。
- **结构感知的 EvidenceRAG**：标题、段落、表格、代码块进入层次化切片；父块负责上下文，子块负责精确检索。
- **多路检索与确定性融合**：BM25、稠密检索、多查询 fan-out、RRF、确定性重排和查询路由组合成可复现管线。
- **证据门控与可核验引用**：每个可核查主张绑定证据片段；系统按覆盖度自动补检索、部分回答或拒答。
- **显式 Agent 状态机**：START → ROUTE → PLAN → RETRIEVE → EVIDENCE_GATE → VERIFY → ANSWER / ABSTAIN → END，全过程有步骤、预算、状态码和恢复点。
- **私有工作空间**：每个账号的资料、索引、任务和产物按空间隔离；共享课程空间由教师/管理员维护。
- **三领域可插拔**：data_structures、general_documents、generic、research_literature、software_engineering 五个领域包复用同一套 Agent 主流程。
- **Skills 双轨制**：6 个产品运行时原生 Skill + 8 个固定版本内置开发参考 Skill，全部有版本、SHA-256、许可证与审计。
- **可下载产物**：回答、学习提纲、文献比较 Markdown/HTML、代码报告与建议 diff 均落盘为 TaskArtifact。
- **可复现实验基础设施**：检索命中、答案支持、Agent 质量三层指标，原始逐例结果保存在 `tests/evaluation/`。

## 科研贡献

### 贡献一：结构感知的证据组织与 Small2Big

传统 RAG 常把文档切成等长块，导致定义、条件与结论被切断。本项目把文档解析为：

- **父块**：保留章节级上下文；
- **子块**：保留最小可检索证据范围；
- **Small2Big**：检索命中子块后，按需读取父块、相邻块或整页来源。

每个 Evidence 记录文档、页码、字符范围、内容哈希、来源版本、权威度、检索分与核验分。这样既能保持召回粒度，又能在生成阶段恢复完整上下文。

**交付证据**：15 页课程 PDF 生成 8 个父块、29 个子块；父子块、来源页与相邻块读取均有自动化测试。

### 贡献二：多路证据获取与确定性融合

系统把检索暴露为有预算的显式动作：

```text
keyword_search
semantic_search
read_child / read_parent / read_siblings / read_source_page
retrieve_conflicting_versions
```

- 查询路由先判断问题类型、代码特征、冲突可能性和上下文长度；
- 首轮执行词法 + 语义候选，使用 RRF 融合；
- 需要更多上下文时补充检索或读取父块 / 相邻块 / 来源页；
- 融合与重排采用确定性策略，便于复现实验；
- 每次尝试记录 provider、model、dimension、index_version、threshold 与 action reason。

**交付证据**：高级检索小样本 9/9 命中、库外 2/2 拒答；平台 19 例 advanced 100%。

### 贡献三：证据门控、主张核验与冲突检测

回答在显式门控之后生成：

- 计算证据覆盖、主张支持、权威度、时效性与冲突数；
- 门控输出 PASS / RETRIEVE_MORE / ABSTAIN；
- 对可核查主张抽取数字、单位、版本、年份与极性；
- 引用核验区分 supported / partially_supported / contradicted / insufficient；
- 冲突检测识别数字、单位、版本、否定与适用范围差异；
- 同一主张的多条证据以轻量关系表达，不引入额外图数据库。

**交付证据**：平台评测冲突检测 5/5，拒答 precision/recall 1.0/1.0，unsupported claim 0。

### 贡献四：显式、可恢复、受预算约束的 Agent 运行层

系统使用可解释的薄 Django 状态机：

```text
START -> ROUTE -> PLAN -> RETRIEVE -> EVIDENCE_GATE
      -> RETRIEVE_MORE / CALL_TOOL / CONFLICT_CHECK
      -> VERIFY -> ANSWER / ABSTAIN -> END
```

- 每个步骤记录 run_id、step_id、parent_id、hop_id、输入输出摘要、evidence_ids、decision、reason_code、延迟、Token、预算与状态码；
- 任务状态覆盖 QUEUED / RUNNING / WAITING_USER / SUCCEEDED / PARTIAL / FAILED / CANCELLED；
- SQLite worker 通过短事务领取任务，lease/heartbeat 防止双执行；
- 取消在步骤间检查，过期租约重新排队，重试创建新 run；
- 预算覆盖步骤、Token、工具调用、延迟与 retrieve-more 循环；
- 仅保存可核查操作记录，不保存完整思维链。

**交付证据**：真实 `workbench_worker` 处理排队任务；取消、重试、刷新恢复、过期租约均有自动化测试。

### 贡献五：可插拔领域包、任务包、工具契约与 Skill 运行层

系统把“领域知识”和“执行方法”拆成四层契约：

| 契约 | 作用 |
| --- | --- |
| **DomainPack** | 领域术语、文档类型、切片策略、元数据、权威/时效策略、提示策略、可用工具、评测案例 |
| **TaskPack** | 任务输入、步骤模板、工具范围、完成条件、结果 schema、检查规则 |
| **ToolSpec** | 版本、输入输出 schema、权限、副作用、超时、预算、幂等性、证据返回规则 |
| **SkillSpec** | 可复用的任务操作方法；只提供方法，不授予权限 |

同一套 Agent 主流程已经在五个领域包上运行：

- `data_structures`：课程知识、练习与共享课程空间；
- `general_documents` / `generic`：个人笔记与自由文档；
- `research_literature`：论文比较与相关文献推荐；
- `software_engineering`：只读代码证据与建议 diff。

Skill 运行层采用渐进加载：按任务选择最多两个 Skill，工具范围取 **TaskPack ∩ DomainPack ∩ Skill 声明 ∩ 已批准 ToolSpec ∩ 当前能力 ∩ 空间权限**。Skill 的工具范围由服务端交集决定，权限边界清晰可审计。

**交付证据**：6 个原生运行时 Skill、8 个固定版本开发参考 Skill、`manage.py skills_audit` 全部校验通过。

### 贡献六：跨领域工作台与可下载产物

工作台把“检索能力”转化为用户可完成的任务闭环：

- **有据问答**：答案、引用、证据抽屉与原文定位；
- **引导式学习**：提纲、分层提示、自测题，与正式判题成绩分离；
- **文献比较**：方法、实验条件、结论、局限四类字段的带引用对照表，输出 Markdown/HTML；
- **代码分析**：文件/行号证据、风险模式、建议 unified diff、执行状态；
- **文献库**：基于本人私有文献与内置离线目录生成相关文献推荐，展示相关词与来源；
- **任务记录**：取消、重试、刷新恢复、反馈和产物下载。

每个产物都经过空间权限校验；文献比较明确声明“范围比较”，代码分析明确声明执行状态。

### 贡献七：分层评测协议

评测拆成三层指标：

| 层级 | 指标 |
| --- | --- |
| **retrieval_hit** | document/page/parent/child/exact span、Recall@k、MRR、nDCG、parent recovery rate |
| **answer_support** | claim-level citation precision/recall、citation coverage、supported claim ratio、unsupported claim rate、contradiction rate、abstention precision/recall |
| **agent_quality** | tool selection、invalid-call rate、permission rejection、recovery rate、trajectory length、unnecessary retrieval、p50/p95 latency、Tokens、cost、tool calls |

每次实验保存 git_sha、config_hash、dataset_hash、model/provider/revision、embedding dimension、index/chunk policy version、seed、metrics、raw trace 与 failure cases。

## 系统架构

```text
Browser (Django Templates + 原生 JS/CSS/SVG)
  -> apps/workspace
       私有空间、成员、资料、上传解析、任务、产物、文献推荐、工作台 API
  -> apps/platform
       DomainPack / TaskPack / ToolSpec / SkillSpec
       Agent 状态机、自适应路由、证据门控、Skill Runtime
  -> apps/knowledge
       层次切片、Small2Big、BM25、稠密检索、RRF、重排、冲突、引用核验
  -> SQLite + Chroma + workbench_worker
```

### 关键设计

- **权限边界**：私有空间只有所有者/成员可读；共享空间所有登录用户可读、教师/管理员可写。
- **索引隔离**：同一文件上传到不同空间使用加盐文档哈希与独立片段 ID；检索按文档作用域过滤。
- **任务运行**：短事务领取、lease/heartbeat、取消检查、过期重排、重试与刷新恢复。
- **产物管理**：回答、对照报告、代码报告与建议 diff 存入 TaskArtifact，下载前校验任务/空间权限。
- **Skills 双轨**：运行时 Skill 参与用户任务；开发参考 Skill 固定在 `agent_skills/vendor/`，用于维护与审计。

## 三分钟体验

```bash
# 本地准备：保留既有数据与配置，并创建 SQLite 快照
/Volumes/半岛铁盒/实验室考核部署/scripts/local_setup.sh

# 启动 Web + 任务 worker
/Volumes/半岛铁盒/实验室考核部署/scripts/local_start.sh

# 状态、诊断与 Skill 审计
/Volumes/半岛铁盒/实验室考核部署/scripts/local_status.sh
/Volumes/半岛铁盒/实验室/.venv/bin/python /Volumes/半岛铁盒/实验室考核部署/scripts/local_doctor.py
cd /Volumes/半岛铁盒/实验室考核部署 && /Volumes/半岛铁盒/实验室/.venv/bin/python manage.py skills_audit
```

打开 `http://127.0.0.1:8010/workbench/`：

1. **资料问答 / 学习**：进入“资料问答示例”，上传资料，提问“循环队列判满条件是什么？”，点击 `[来源1]` 查看原文；切换到“引导式学习”生成提纲与自测。
2. **文献比较**：进入“文献比较示例”，选择“文献比较”，输入“比较这些论文的方法与局限”，下载 Markdown/HTML 报告。
3. **代码分析**：进入“代码分析示例”，输入“库存扣减的异常处理有什么问题？”，查看文件/行号证据、建议 diff 与执行状态。

## 评测结果

### 自动化回归

```text
430 passed
```

### 工作台三领域开发集

| 指标 | 结果 |
| --- | --- |
| 案例 | 11（8 条有依据回答 / 3 条正确拒答） |
| answerability accuracy | **1.0** |
| retrieval recall mean | **1.0** |
| MRR mean | **0.9375** |
| citation presence（可答） | **1.0** |
| 案例通过率 | **100%** |

### 平台评测

- advanced 19 例：**100%**
- 冲突检测：**5/5**
- 拒答 precision / recall：**1.0 / 1.0**
- unsupported claim：**0**

### 浏览器验收

- 1440 / 390 / 768 / 1920 四种宽度通过
- 私有空间创建、上传、检索、引用定位、文献比较下载、代码分析下载、刷新恢复与重试通过
- 浏览器控制台：**全部正常**

## 复现实验

```bash
cd /Volumes/半岛铁盒/实验室/AlgoMentor
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py check
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py migrate
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py skills_audit
/Volumes/半岛铁盒/实验室/.venv/bin/python -m pytest -q
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py seed_workbench_demo --username demo_student
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py evaluate_workbench --username demo_student
python scripts/evaluate_evidence_rag.py
python scripts/evaluate_platform.py
```

原始结果：

- `tests/evaluation/workbench_results.json`
- `tests/evaluation/evidence_rag_results.json`
- `tests/evaluation/platform_results.json`

## 代码入口

| 模块 | 位置 |
| --- | --- |
| 私有空间与权限 | `apps/workspace/models.py`、`permissions.py`、`services/workspaces.py` |
| 资料上传与解析 | `apps/workspace/services/documents.py`、`apps/knowledge/services/advanced_index_service.py` |
| 工作台页面与 API | `apps/workspace/views.py`、`templates/workbench/index.html`、`static/js/workbench.js` |
| 任务队列与执行 | `apps/workspace/services/tasks.py`、`services/executor.py`、`management/commands/workbench_worker.py` |
| 文献库与推荐 | `apps/workspace/services/literature.py`、`knowledge/literature_catalog.json` |
| 领域包与任务包 | `apps/platform/domains/`、`apps/platform/contracts/` |
| Agent 状态机 | `apps/platform/agent/state_machine.py`、`adaptive_router.py` |
| 运行时 Skills | `apps/platform/skills/runtime.py`、`agent_skills/registry.json`、`agent_skills/runtime/` |
| 开发参考 Skills | `agent_skills/vendor/`、`agent_skills/development/index.json`、`apps/platform/skills/development.py` |
| Skill 审计 | `manage.py skills_audit`、`skills.lock.json`、`THIRD_PARTY_NOTICES.md` |
| 工作台评测 | `apps/workspace/evaluation/cases.py`、`manage.py evaluate_workbench` |
| 部署与诊断 | `scripts/local_setup.sh`、`local_start.sh`、`local_stop.sh`、`local_status.sh`、`local_doctor.py` |

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Django、SQLite、Python 3.12 |
| 检索 | Chroma、BM25、TF-IDF 本地词法基线、RRF、确定性重排 |
| Agent | 自研显式状态机、DomainPack / TaskPack / ToolSpec / SkillSpec |
| 前端 | Django Templates、原生 CSS / JavaScript / SVG，宋体优先字体栈 |
| 任务 | SQLite worker、lease/heartbeat、预算、取消、重试、checkpoint |
| 测试 | pytest、Django test client、真实浏览器旅程 |

## 文档

- [ARCHITECTURE.md](ARCHITECTURE.md)：模块边界与运行层设计
- [TESTING.md](TESTING.md)：测试范围与验收记录
- [docs/deployment/LOCAL_DEPLOYMENT.md](docs/deployment/LOCAL_DEPLOYMENT.md)：本地部署、启动、停止与回滚
- [docs/deployment/NETWORK_DNS.md](docs/deployment/NETWORK_DNS.md)：本机 DNS 诊断与修复
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)：内置第三方 Skill 的来源、许可与审计
- [skills.lock.json](skills.lock.json)：固定 commit 与 SHA-256 锁文件

## 致谢

感谢 Django、Chroma、LangChain 及所有开源社区贡献者。开发参考 Skill 的来源、固定 commit 与许可证记录在 `THIRD_PARTY_NOTICES.md` 与 `skills.lock.json`。
