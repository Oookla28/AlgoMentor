---
name: evidence-paper-comparison
version: 1.0.0
description: 对工作空间内至少两篇文献做统一字段比较，所有结论绑定原文证据，缺失字段不臆测。
allowed-tools: [keyword_search, semantic_search, read_child, read_parent, read_siblings]
triggers: [文献比较, 方法对比, 实验条件对比, 局限]
not-triggers: [系统综述, 元分析, 未上传全文的论文总结]
outputs: [comparison_table, per_field_evidence, missing_fields, caveats]
failure_behavior: 只有一篇或零篇可用文献时拒绝生成对照表，并给出补充资料建议。
---

# 文献证据比较

## 适用场景

用户已上传至少两篇论文，希望比较方法、实验设置、数据集、结论与局限。

## 操作步骤

1. 确认每篇文献都有可检索正文；只有标题/摘要时明确标注“仅摘要”。
2. 对每篇文献分别检索方法、数据集、评价指标、主要结论、局限五个字段。
3. 只填写能从原文片段核实的字段；缺失就写“原文未报告/未获得”，不跨文献补齐。
4. 比较实验条件时检查数据集规模、基线、评价口径和计算预算是否可比。
5. 输出 Markdown 表格，并为每个单元格保留来源编号；同时生成 HTML 版本供下载。
6. 明确声明：这是“上传文献的范围比较”，不是系统综述。

## 输出契约

- `comparison_table`：行=文献，列=方法/数据/指标/结论/局限。
- `per_field_evidence`：字段到证据 ID 的映射。
- `missing_fields`：缺失字段列表。
- `caveats`：不可比因素、版本差异与摘要限制。

## 领域限制

临床研究的分级框架不能机械套用到计算机实验；不把“未报告”判为“未执行”。

## 反例

- 用模型记忆补全某篇论文的实验数字。
- 把三篇自选文献称为“覆盖该领域的系统综述”。
