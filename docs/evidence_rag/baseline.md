# EvidenceRAG Studio 基线记录

本文件记录在增量开发开始前对 AlgoMentor 的审计结果。基线数据来自未修改的
上游快照，新增功能不与基线结果混合统计。

## 1. 仓库与版本

| 项目 | 值 |
| --- | --- |
| 上游快照提交 | `423b644`（baseline: import upstream AlgoMentor snapshot） |
| 基线 HEAD | `e710827`（仅移除 macOS AppleDouble 元数据文件） |
| 功能分支 | `feat/evidence-rag-studio` |
| Python | 3.12.16 |
| Django | 5.2.14 |
| 数据库 | SQLite（`data/db.sqlite3`） |
| 时区 | Asia/Shanghai |

> 运行环境说明：本机系统 Python 为 3.9.6，而项目依赖 Django 5.2（要求
> Python ≥ 3.10）。为完成真实验证，使用独立 CPython 3.12.16 运行时与
> `.venv` 安装锁定依赖。该运行时位于仓库外的 `../runtime`，不进入交付代码。

## 2. 基线命令与结果

| 命令 | 结果 |
| --- | --- |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check` | `No changes detected` |
| `pytest -q` | **320 passed, 2 skipped**（52.84s） |
| `python scripts/verify_environment.py` | 通过；Django/langchain/chromadb/crewai/sentence-transformers 等版本可读取 |
| `python scripts/verify_offline.py` | **FAILED**：`OperationalError: unable to open database file` |

### 2.1 跳过项

| 测试 | 跳过原因 |
| --- | --- |
| `tests/integration/test_live_execution.py` | 需要显式启用本机 Piston 真实评测 |
| `tests/integration/test_live_wikipedia_agent.py` | 仅限显式启用的 Wikimedia 在线集成 |

### 2.2 离线探测失败原因

`scripts/offline_probe.py` 会以只读方式复制 `data/db.sqlite3` 并启动全新
WSGI 进程。初始仓库快照不包含 `data/` 目录，因此基线探测在打开数据库时
失败。初始化本地数据库后，本机仍缺少以下环境能力，故离线探测保持
**UNVERIFIED / 环境受限**，而不是被新代码破坏：

- 本地 BGE 权重（`BAAI/bge-small-zh-v1.5`）未预下载；
- 本机未部署离线 Piston/Isolate；
- 本机未预热 Wikipedia 公共缓存。

这些限制在基线阶段已存在，未通过修改代码或伪造结果绕过。

环境初始化后的复跑（显式使用 `EMBEDDING_PROVIDER=tfidf`、
`CHROMA_PATH=/tmp/algomentor-chroma`、`RAG_MIN_SCORE=0.2`，并执行
`collectstatic`、预热“红黑树”缓存）结果：

- 页面、静态资源、图谱、课程检索、百科缓存、网络失败回退、服务状态与
  算法接口均通过；
- 在“本机隔离执行”步骤失败：
  `CodeExecutionError: 无法连接隔离执行服务；本次不计入成绩。`
- 说明：失败点是本机未部署 Piston/Isolate，而不是 EvidenceRAG 代码；
  默认 BGE 路径仍需本地权重，因此离线探针整体仍标记为
  **ENVIRONMENT-LIMITED / UNVERIFIED**。

## 3. 基线知识库与检索配置

| 配置 | 基线值 |
| --- | --- |
| `EMBEDDING_PROVIDER` | `bge`（可显式改为 `tfidf` 基线） |
| `EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` |
| `EMBEDDING_REVISION` | `main` |
| `LOCAL_EMBEDDING_OFFLINE_MODE` | `true` |
| `CHROMA_PATH` | `data/chroma` |
| `RAG_TOP_K` | 4 |
| `RAG_MIN_SCORE` | 0.45 |
| 旧版 collection | `course-<sha256(document_hash + embedding_identity)[:24]>` |
| 旧版切片 | `RecursiveCharacterTextSplitter(chunk_size=650, chunk_overlap=80)` |
| 旧版页面 | 15 页 PDF，35 个片段，512 维（BGE 实际索引） |

## 4. 基线已实现功能

- 课程 PDF 入库、Chroma 稠密检索、Citation 与 `[来源N]` 引用校验；
- LangChain Agent 工具调用与 DeepSeek BYOK；
- CrewAI 学习报告；
- 在线代码评测与判题适配器；
- 知识图谱、掌握度追踪、BKT/规则估计；
- Wikipedia 在线检索与公共缓存；
- 离线本地学习模式；
- Django Templates + 原生 CSS/JS 前端；
- 218 项历史验收记录中列出的页面与接口保护。

## 5. 基线缺失功能（本次增量目标）

- 文档/图片/视频统一入库与 MIME 适配；
- 结构感知递归切片、父块/子块、Small2Big；
- BM25 稀疏检索、多查询 Fan-out、RRF、可选交叉编码器重排；
- 查询路由与查询改写（含无 LLM 的确定性回退）；
- 检索轨迹、知识片段可视化与管理员 CRUD；
- 图片 OCR/人工标注、视频 ASR/关键帧/时间戳证据；
- 主张抽取、冲突检测、权威性与时效性仲裁；
- claim 级引用核验、无证据拒答与生成契约；
- EvidenceRAG 单元/集成/回归测试与评测脚本；
- README / ARCHITECTURE / IMPLEMENTATION_PLAN / TESTING / DELIVERY_REPORT 同步。

## 6. 外部服务状态（基线）

| 服务 | 状态 |
| --- | --- |
| DeepSeek | 未调用；无共享 Key，按用户 BYOK |
| Wikipedia | 未在基线测试中实时调用 |
| Piston / Judge0 | 未在基线测试中真实调用 |
| 本地 BGE | 权重未就绪，离线模式禁止隐式下载 |
| 本地 Chroma | 旧版索引可在测试临时目录中真实构建与查询 |

## 7. 基线保护约束

后续增量必须继续保持：

- 不删除、不重命名现有模型字段，不修改已有迁移；
- `retrieve_knowledge(query, top_k)` 的返回类型与 Citation 旧字段不变；
- 旧搜索 API 字段不变，新增字段只做增量；
- `[来源N]` 与 `verified_citation_ids()` 语义不变；
- 不覆盖旧 Chroma collection，不改变旧索引维度；
- 不修改 `templates/base.html` 与 `static/css/app.css` 的全局视觉系统；
- 学生页面不出现管理员维护入口，不暴露 traceback、服务器路径或 API Key。
