# AlgoMentor V2 续建盘点（P0）

生成时间：2026-11-08（Asia/Shanghai）
本轮基线提交：`1c927e0`（`main`，工作区干净）
续建前测试基线：`398 passed, 2 skipped`
续建后测试结果：`422 passed, 2 skipped`（同一测试环境，真实运行）

## 1. 目录与 Git 事实

| 项目 | 路径 | 事实 |
| --- | --- | --- |
| 源仓库 | `/Volumes/半岛铁盒/实验室/AlgoMentor` | `main`；本轮从 `1c927e0` 增量开发，未推送远端 |
| 本地交付 | `/Volumes/半岛铁盒/实验室考核部署` | 无 `.git`；原有代码约 `c2a9c71`，已有 SQLite 数据、证据上传目录与运行日志 |
| 既有服务 | `http://127.0.0.1:8010/` | 续建前由 `runserver --noreload` 运行；PID 记录在 `data/run/server.pid` |
| 既有演示账户 | `demo_student` / `demo_staff` | 密码为既有本地部署值，本轮未重置、未写入文档 |

未执行：`git push`、`git reset --hard`、`git clean -fd`、删除数据库、覆盖 `.env`、重建加密主密钥。

## 2. 逐项状态

图例：
- `EXISTING_VALIDATED`：续建前已存在，且有本轮之前的运行/测试记录。
- `IMPLEMENTED_UNVERIFIED`：本轮新增或修改，代码与自动化测试存在，但真实浏览器/外部依赖尚未最终验收。
- `MISSING`：本轮开始时不存在。
- `BLOCKED`：受环境凭据/服务限制，无法真实验收。

| 能力 | 状态 | 代码位置 | 证据/说明 |
| --- | --- | --- | --- |
| 层次化切片、父子块、Small2Big | EXISTING_VALIDATED | `apps/knowledge/services/hierarchical_chunker.py`、`small2big_service.py` | 既有测试与 15 页 PDF 记录；本轮回归通过 |
| BM25 + 稠密/RRF/重排/门控 | EXISTING_VALIDATED | `apps/knowledge/services/hybrid_retrieval.py`、`sparse_retrieval.py`、`rerank_service.py` | 既有 advanced 9/9 smoke；本轮回归通过 |
| 冲突检测、引用核验、管理员 CRUD | EXISTING_VALIDATED | `conflict_service.py`、`citation_verifier.py`、`views_evidence.py` | 既有测试；本轮回归通过 |
| 平台领域包/任务包/工具契约 | EXISTING_VALIDATED | `apps/platform/contracts/`、`domains/`、`tools/` | 本轮扩展为五领域包；原两包保持 |
| 显式 Agent 状态机 | EXISTING_VALIDATED | `apps/platform/agent/state_machine.py` | 新增 workspace scope、取消检查、既有运行复用；原 API 行为保持 |
| 能力探针 | EXISTING_VALIDATED | `apps/platform/capabilities.py` | 新增 Skill/worker 状态在独立接口中展示 |
| 私有工作空间与成员 | MISSING → IMPLEMENTED_UNVERIFIED | `apps/workspace/models.py`、`permissions.py`、`services/workspaces.py` | 自动化测试覆盖所有者/成员/共享只读/越权 API |
| 个人资料上传与检索隔离 | MISSING → IMPLEMENTED_UNVERIFIED | `apps/workspace/services/documents.py`、`apps/knowledge/services/advanced_index_service.py` | 文档哈希按 workspace 加盐；词法检索按 document_ids 过滤；Chroma 检索按 document_hash 过滤 |
| 资料解析状态、失败重试、软移除/恢复 | MISSING → IMPLEMENTED_UNVERIFIED | `WorkspaceDocument`、`workspace/views.py` | 同步解析；失败保留文件与重试入口；移除后立即退出检索范围 |
| 任务持久化、队列、租约、取消、重试 | MISSING → IMPLEMENTED_UNVERIFIED | `apps/platform/models.py`（AgentRun 扩展）、`apps/workspace/services/tasks.py`、`management/commands/workbench_worker.py` | 真实 CLI worker 已处理排队任务；取消/过期租约/重试用例通过 |
| 文献比较产物 | MISSING → IMPLEMENTED_UNVERIFIED | `apps/workspace/services/executor.py` | 真实 TF-IDF 演示集：3 篇文献，Markdown+HTML 产物，缺失字段标注；未做系统综述 |
| 代码调查与建议 diff | MISSING → IMPLEMENTED_UNVERIFIED | `executor.py`、`artifacts.py` | 只读静态证据；执行状态固定 `UNVERIFIED`；建议 diff 可下载，不自动应用 |
| 引导式学习 | MISSING → IMPLEMENTED_UNVERIFIED | `executor.py` | 抽取式提纲、提示、自测；明确不更新掌握度、不是正式题库 |
| Skill Runtime | MISSING → IMPLEMENTED_UNVERIFIED | `apps/platform/skills/runtime.py`、`agent_skills/` | 6 个原生 Skill；YAML `safe_load`、路径/符号链接/大小限制、工具权限交集；正反例与依赖缺失测试 |
| 上游开发 Skill 参考 | MISSING → BLOCKED（仅参考） | `skills.lock.json`、`THIRD_PARTY_NOTICES.md` | 本机 DNS 不可用，无法读取上游文件；未下载、未安装、未伪造 hash |
| 工作台 UI | MISSING → IMPLEMENTED_UNVERIFIED | `templates/workbench/index.html`、`static/js/workbench.js`、`static/css/workbench.css` | 空间切换、上传、任务阶段、引用、证据抽屉、产物下载、取消/重试、草稿恢复 |
| 三领域演示资料 | MISSING → IMPLEMENTED_UNVERIFIED | `knowledge/workspace_demo/`、`seed_workbench_demo` | 资料问答 1 份、文献 3 份、代码 2 份；可重复执行且不覆盖既有私空间 |
| 工作台开发集评测 | MISSING → IMPLEMENTED_UNVERIFIED | `apps/workspace/evaluation/`、`evaluate_workbench` | 11 条手写案例；真实运行结果在 `tests/evaluation/workbench_results.json` |
| 全局字体 | 修改 | `static/css/app.css`、`static/css/evidence-rag.css`、两处模板内联样式 | 统一为宋体优先栈；主题、布局、间距不变 |
| BGE / Cross-Encoder | BLOCKED / UNVERIFIED | `embedding_service.py`、`capabilities.py` | 未准备权重，未把 TF-IDF 称为 BGE |
| 在线 LLM 生成 | BLOCKED / NOT CONFIGURED | BYOK 既有链路 | 本轮不调用付费模型；抽取式结果不冒充生成式 |
| OCR / ASR / 关键帧 | BLOCKED / UNVERIFIED | `multimodal_loader.py` | 依赖未验证；只保留适配与人工标注边界 |
| Piston 代码执行 | BLOCKED / UNVERIFIED | 既有执行适配 | 产品任务不执行用户代码；代码分析明确 `UNVERIFIED` |
| 生产多租户安全 | BLOCKED | — | 本地预览只监听 `127.0.0.1`，未做公网/生产验收 |

## 3. 本轮新增测试

- `apps/workspace/tests/test_workspace_permissions.py`：私有/共享/成员权限、移除文档退出检索范围、跨空间任务拒绝。
- `apps/workspace/tests/test_skill_runtime.py`：Skill 目录、选择、权限交集、路径穿越、符号链接、超大文件、注册表缺失降级。
- `apps/workspace/tests/test_workspace_tasks.py`：真实状态机问答、拒答、取消、重试、过期租约、文献比较产物、代码调查与建议 diff。
- `apps/workspace/tests/test_workbench_api.py`：工作台页面、空间 API、任务 API、跨用户 403、产物下载隔离、私有原文访问控制、共享空间只读。

## 4. 未验证与限制

1. 真实浏览器旅程需在实际部署 URL 上完成；本轮代码阶段只做了 HTTP/单元/集成测试。
2. BGE、Cross-Encoder、在线 LLM、OCR/ASR、关键帧、Piston 均未真实验收。
3. 工作台评测集为 11 条手写开发样例，不是 120–180 条人工标注集；不能作为泛化结论。
4. 文献比较只覆盖已上传正文，不构成系统综述。
5. TF-IDF 向量器按索引版本首次拟合后复用；新增资料可能被词表外词限制，词法检索仍可用。这是明确限制，不是 BGE 语义能力。
6. 资料解析在请求内同步完成；大文件会延长单次上传请求时间，尚未改为独立解析队列。
