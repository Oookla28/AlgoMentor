# EvidenceRAG / Platform 评测协议

## 2026-11-08 追加：工作台三领域开发集

- 数据：`apps/workspace/evaluation/cases.py`，11 条手写案例（8 条可答、3 条不可答），覆盖 generic / research_literature / software_engineering。
- 每次运行保存：git SHA、config hash、dataset hash、embedding provider/model/revision、逐例原始结果、阶段摘要、引用、产物数量、失败原因。
- 指标：
  - `retrieval_recall`：gold term 在工作台证据/产物中的覆盖率（gold term 是原文短语，不是 chunk_id）。
  - `mrr`：首条含 gold term 的证据排名倒数。
  - `answerability_accuracy`：可答问题有引用且非拒答；不可答问题拒答/部分拒答。
  - `citation_presence_rate_answerable`：可答问题的引用出现率。
  - `unsupported_claim_rate`：`verify_answer` 的无支持主张比例。
  - `latency_p50/p95`、`tool_calls`、`steps`、`skill activations`。
- 当前结果（部署环境，TF-IDF）：answerability **1.0**、Recall **1.0**、MRR **0.9375**、unsupported claim **0.0455**、p50 **628 ms** / p95 **6094 ms**；逐例见 `tests/evaluation/workbench_results.json`。
- 解释边界：开发集规模小；案例由本项目编写，未做多人独立标注；TF-IDF 是词法基线，不是 BGE；代码分析没有真实隔离执行，执行状态为 `UNVERIFIED`；文献比较不是系统综述。


## 1. 目的与边界

本协议用于区分三类问题：

1. **检索命中**：正确证据是否被召回；
2. **回答支撑**：回答中的 claim 是否有可核验 evidence；
3. **Agent 质量**：工具选择、拒答、预算、延迟与错误恢复是否可控。

当前数据规模小（课程 PDF 15 页 + 19 个平台案例），结果只能作为
**smoke / 工程验证**，不能写成生产准确率、BGE 泛化结论或学习效果因果结论。

## 2. 数据格式

`tests/evaluation/platform_cases.json` 每个 case 支持：

| 字段 | 含义 |
| --- | --- |
| `case_id` | 稳定 ID |
| `question` | 问题 |
| `domain` | 领域包 ID |
| `difficulty` | easy / medium / hard / out-of-corpus |
| `answerable` | 是否可由课程资料回答 |
| `gold_evidence` | `pages`、`text`、`parent_pages` |
| `atomic_claims` | 期望的原子 claim |
| `required_citations` | 最少引用数 |
| `hard_negatives` | 同页/近邻误导概念 |
| `conflict_type` | negation / numeric / unit / version / temporal / misleading |
| `modality` | text / image / video |
| `required_tools` | 期望使用的工具 |
| `expected_abstention` | 是否应拒答 |
| `synthetic_claims` | 规则冲突评测用的合成 claim |

覆盖类型：同页近邻（队空/队满）、误导条件、跨页 multi-hop、库外拒答、
否定/数字/单位/版本/年份冲突。

## 3. 指标

### 3.1 retrieval_hit

- **Hit@k**：top-k 是否含 gold evidence；
- **Recall@k**：gold 证据被召回比例；
- **MRR**：首个相关证据的倒数排名；
- **nDCG@k**：二值相关性下的归一化折损累计增益；
- **parent recovery rate**：是否恢复命中子块的父块/父级页面；
- **refusal rate**：库外问题是否返回空证据。

### 3.2 answer_support

- claim coverage / citation coverage；
- supported claim ratio / unsupported claim rate；
- contradiction rate / answer faithfulness；
- abstention precision / recall；
- Brier / ECE（当前为 coverage-based proxy，未校准）。

### 3.3 agent_quality

- avg steps、avg tool calls；
- p50 / p95 latency；
- invalid call rate（`TOOL_FAILED` 步骤 / 工具步骤）；
- permission rejection、timeout、invalid tool probe；
- conflict cases detected / total；
- 预算拒答（`BUDGET_EXCEEDED`）。

## 4. 实验矩阵

| 编号 | 配置 | 当前状态 |
| --- | --- | --- |
| B0 | legacy dense | RUNNABLE |
| B1 | advanced + TF-IDF | RUNNABLE |
| B2 | advanced + BGE | UNVERIFIED（缺本地权重） |
| B3 | B2 + cross-encoder | UNVERIFIED（依赖 B2） |
| B4 | B3 + adaptive routing | UNVERIFIED（依赖 B2；TF-IDF adaptive 仅工程探针） |
| B5 | B4 + conflict-aware verifier | UNVERIFIED（依赖 B2） |

每次运行必须保存：`git_sha`、`config_hash`、`dataset_hash`、
`model/provider/revision`、embedding dimension、index/chunk policy version、
seed、metrics、raw per-case summary、failure cases。

## 5. 命令

```bash
python scripts/evaluate_evidence_rag.py
python scripts/evaluate_platform.py
```

结果：

- `tests/evaluation/evidence_rag_results.json`
- `tests/evaluation/platform_results.json`

## 6. 当前实际结果（TF-IDF）

| 指标 | 值 |
| --- | --- |
| 平台案例 | 19 |
| legacy hit rate | 0.75 |
| advanced hit rate | 1.00 |
| advanced MRR | 0.806 |
| parent recovery | 1.00 |
| legacy / advanced 库外拒答 | 1.00 / 1.00 |
| claim coverage | 0.976 |
| unsupported claim rate | 0.00 |
| abstention precision / recall | 1.00 / 1.00 |
| conflict cases detected | 5 / 5 |
| tool probes | permission denied / timeout / not found 均按预期 |
| avg steps / tool calls | 11.14 / 2.0 |
| p50 / p95 latency | 226 ms / 246 ms |

## 7. 解释规则

- 不允许把 TF-IDF 9/9 或平台 100% 写成 BGE 结论；
- 不允许把一次在线调用写成泛化实验；
- 不允许把检索指标写成学习效果；
- 必须报告失败 case、环境限制与未执行矩阵项；
- 任何“Validated”必须有脚本/测试产物；否则标记 Optional / Unverified /
  Environment-limited。
