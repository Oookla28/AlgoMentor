# 下一阶段前的冻结基线

日期：2026-11-08  
源目录：`/Volumes/半岛铁盒/实验室/AlgoMentor`  
分支：`main`  
Commit：`9cabf27`（EvidenceRAG Studio 第一个可运行版本；本文件生成时工作区尚未包含平台化增量）

## 1. 环境

| 项目 | 值 |
| --- | --- |
| Python | 3.12.16（独立运行时，仓库外 `.venv`） |
| Django | 5.2.14 |
| 数据库 | SQLite（本地演示库） |
| 向量库 | Chroma 1.5.9，验证路径 `/tmp/algomentor-chroma` |
| Embedding | TF-IDF char 1–3 gram，2048 维（BGE 未验证） |
| 分支 | `main`（本地）；远端 `feat/evidence-rag-studio` 已存在 |

说明：宿主机与 `/Volumes/半岛铁盒` 外接卷上的 Chroma 可能因 SQLite 文件锁失败；
验证时显式使用 `/tmp/algomentor-chroma`。这是环境限制，不是代码通过条件。

## 2. 基线命令与真实结果

| 命令 | 结果 |
| --- | --- |
| `python manage.py check` | 无问题 |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `pytest -q` | **371 passed, 2 skipped** |
| `python scripts/evaluate_evidence_rag.py` | **PASSED**：advanced 9/9，库外拒答 2/2；legacy 6/9，拒答 2/2 |
| 关键页面/API smoke | 11 个页面 HTTP 200；legacy 搜索 200；空查询 400；未登录 401 |
| 依赖检查 | `pip check`：无冲突 |

2 个 skip 仍为：

- `tests/integration/test_live_execution.py`：需要显式本机 Piston；
- `tests/integration/test_live_wikipedia_agent.py`：显式 Wikimedia 在线集成。

没有 pre-existing 测试失败。新增失败必须先修复再继续。

## 3. 能力状态（真实探针）

| 能力 | 状态 | 原因 |
| --- | --- | --- |
| database | available | SQLite |
| legacy_index | available | 1 个文档，旧版索引 |
| advanced_index | available | `adv-3276aef3b4b6faa840345085`，29 个向量 |
| embedding | fallback | TF-IDF 词法基线，不是 BGE |
| reranker | available | deterministic |
| llm | not-configured | 按用户 BYOK，未做网络探测 |
| piston | environment-limited | `127.0.0.1:2000` 未开放 |
| ocr | disabled | pytesseract / tesseract 缺失 |
| asr | disabled | faster-whisper / ffmpeg 缺失 |
| keyframes | disabled | opencv / ffmpeg 缺失 |
| wikipedia | unverified | 未做网络探测 |

## 4. 检索评测逐例归因

9 个库内问题：advanced 9/9；legacy 6/9。legacy 的 3 个失败均为
**TF-IDF 词法基线 + top-k/阈值**导致命中片段未覆盖 gold page/text，
不是接口错误或索引缺失：

| case | query | legacy 结果 | advanced 结果 | 归因 |
| --- | --- | --- | --- | --- |
| queue-full | 循环队列判满条件 | 3 条，但未命中第 9 页 `rear + 1` | 命中 | 词法召回偏向相邻“队空/指针”片段 |
| linked-list | 单链表节点包含哪两个域 | 1 条，未命中第 5/6 页 `指针域` | 命中 | 稀疏词法无法覆盖同义表述 |
| stack-lifo | 栈为什么是后进先出 | 1 条，未命中第 7/8 页 `后进先出` | 命中 | 单路稠密 TF-IDF 语义不足 |

2 个库外问题：legacy 与 advanced 均 2/2 拒答。

## 5. Golden snapshot

- `docs/evidence_rag/golden/legacy_api_snapshot.json`
- 记录旧搜索 API：
  - 顶层字段：`query`、`results`、`citations`、`evidence_sufficient`、`embedding_provider`
  - Citation 仅 11 个旧字段（新增字段不进入 legacy JSON）
  - 命中 200、空查询 400、未登录 401、空结果 `evidence_sufficient=false`
  - 页面 smoke 全部 200。

## 6. 部署目录

P0 时 `/Volumes/半岛铁盒/实验室考核部署` **不存在**。P8 将创建并记录备份/回滚策略；
本文件不声称部署已完成。

## 7. 基线冻结结论

- 旧链路可运行、测试无失败、legacy schema 已冻结；
- advanced TF-IDF 链路可运行，但只作为工程/词法基线；
- BGE、Cross-Encoder、LLM、OCR、ASR、关键帧、Piston、在线生成均不得标记为已验证；
- 后续平台化增量必须在以上基线上增加，不得破坏 legacy 字段、排序、错误码与空结果语义。
