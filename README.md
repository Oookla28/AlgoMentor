# 数构智学 · AlgoMentor

<p align="center"><strong>可插拔领域知识包的 Evidence-Grounded Agent 学习工作台</strong></p>

AlgoMentor 把课程学习、私有资料空间、证据检索、任务执行与可核验产物整合在一个 Django 应用中。学生可以继续使用原有课程、搜索、聊天、判题、错题、知识网络与学习报告；同时可以建立自己的私有空间，上传课程笔记、论文或代码资料，提交有据问答、引导式学习、文献比较与代码分析任务，并获得带原文引用的回答和可下载产物。

## 核心能力

- **课程学习**：课程知识库、AI 助教、在线判题、错题本、掌握度、知识网络、算法可视化、学习报告。
- **私有工作空间**：每个账号拥有独立空间，资料上传、解析、检索、任务与产物都按空间隔离；共享课程空间由教师/管理员维护。
- **Evidence 工作台**：左侧导航提供 Evidence 工作台、我的空间、文献库、代码分析四个入口。
- **有据问答**：检索资料原文，逐条给出 `[来源N]` 引用，点击即可回到原文位置。
- **引导式学习**：从资料生成学习提纲、分层提示与自测题，并与正式判题成绩分开。
- **文献库**：管理当前空间论文，基于关键词从本人其他私有文献与内置离线目录推荐相关论文，展示推荐依据与来源。
- **文献比较**：按方法、实验条件、主要结论、局限生成带引用的 Markdown/HTML 对照报告。
- **代码分析**：在只读边界内定位代码证据，输出风险、建议 diff 与明确的执行状态；补丁经人工确认后使用。
- **任务运行层**：QUEUED / RUNNING / WAITING_USER / SUCCEEDED / PARTIAL / FAILED / CANCELLED 状态流转，支持取消、重试、刷新恢复、租约与预算。
- **Skills**：6 个产品运行时原生 Skill + 8 个固定版本内置开发参考 Skill，全部通过 SHA-256 审计。
- **领域扩展**：data_structures、general_documents、generic、research_literature、software_engineering 五个领域包；同一套 Agent 主流程跨领域工作。

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

## 架构

```text
Browser (Django Templates + 原生 JS/CSS/SVG)
  -> apps/workspace  私有空间、资料、任务、产物、文献推荐
  -> apps/platform   领域包、任务包、工具契约、Agent 状态机、Skills
  -> apps/knowledge  层次切片、BM25 + 稠密检索、RRF、证据门控、引用核验
  -> SQLite + Chroma + workbench_worker
```

- **权限边界**：私有空间只有所有者/成员可读；共享空间所有登录用户可读、教师/管理员可写。
- **索引隔离**：同一文件上传到不同空间使用加盐文档哈希与独立片段 ID；检索按文档作用域过滤。
- **显式状态机**：START → ROUTE → PLAN → RETRIEVE → EVIDENCE_GATE → RETRIEVE_MORE / CALL_TOOL / CONFLICT_CHECK → VERIFY → ANSWER / ABSTAIN → END。
- **任务持久化**：SQLite 短事务领取、lease/heartbeat、取消检查、过期重排、重试与刷新恢复。
- **Skill 运行时**：按任务懒加载，工具范围取 TaskPack ∩ DomainPack ∩ ToolSpec ∩ 当前能力 ∩ 空间权限。
- **产物**：回答、文献对照、代码报告与建议 diff 存入 TaskArtifact，下载按任务/空间权限校验。

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

## 能力清单

| 能力 | 交付状态 | 说明 |
| --- | --- | --- |
| 旧版课程、搜索、聊天、判题、错题、知识网络、报告 | **已交付并验证** | 完整回归 430 项自动化测试通过 |
| 私有工作空间、成员/共享只读、上传解析状态 | **已交付并验证** | 上传、检索、移除、恢复与跨用户访问控制均已验收 |
| 任务队列、worker、租约、取消、重试、刷新恢复 | **已交付并验证** | 真实 worker 处理排队任务；浏览器刷新与重试流程通过 |
| 有据问答 / 引导学习 / 文献比较 / 代码分析 | **已交付并验证** | 三领域演示与浏览器旅程通过 |
| 左侧导航：工作台 / 我的空间 / 文献库 / 代码分析 | **已交付并验证** | 子项缩进、当前项高亮；桌面与移动端验收通过 |
| 账号独立云空间与文献库 | **已交付并验证** | 私有/共享分组；跨用户推荐与 API 访问控制通过 |
| 基于上传文献的相关文献推荐 | **已交付并验证** | 关键词重叠；本人私有文献 + 内置离线目录；展示相关词与来源 |
| Skill Runtime + 6 个原生 Skill | **已交付并验证** | 懒加载、版本/hash、工具权限交集、路径与符号链接校验 |
| 8 个上游开发参考 Skill 内置 | **已交付并审计** | 固定 commit、正文/许可证 SHA-256、`skills_audit` 校验 |
| 结构感知切片、Parent/Child、Small2Big | **已交付并验证** | 15 页课程 PDF 生成 8 父块 / 29 子块 |
| BM25 + 稠密检索 + 多查询 + RRF + 确定性重排 | **已交付并验证** | 高级检索小样本 9/9 命中、库外 2/2 拒答 |
| 证据门控、无证据拒答、冲突检测 | **已交付并验证** | 平台 19 例：冲突 5/5，拒答 precision/recall 1.0/1.0 |
| 全局宋体字体与统一视觉 | **已交付并验证** | 灰白/青绿主题、卡片语言与响应式布局保持统一 |

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

### 浏览器验收

- 1440 / 390 / 768 / 1920 四种宽度通过
- 私有空间创建、上传、检索、引用定位、文献比较下载、代码分析下载、刷新恢复与重试通过
- 浏览器控制台：**全部正常**

## 快速开始

```bash
cd /Volumes/半岛铁盒/实验室/AlgoMentor
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py check
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py migrate
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py skills_audit
/Volumes/半岛铁盒/实验室/.venv/bin/python -m pytest -q
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py seed_workbench_demo --username demo_student
/Volumes/半岛铁盒/实验室/.venv/bin/python manage.py evaluate_workbench --username demo_student
```

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Django、SQLite、Python 3.12 |
| 检索 | Chroma、BM25、TF-IDF 本地词法基线、RRF、确定性重排 |
| Agent | 自研显式状态机、TaskPack / DomainPack / ToolSpec / SkillSpec |
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
