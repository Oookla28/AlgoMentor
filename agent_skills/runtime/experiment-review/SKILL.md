---
name: experiment-review
version: 1.0.0
description: 检查资料中的实验复现条件、数据泄漏、对照公平性和失败案例，按领域调整检查项。
allowed-tools: [keyword_search, semantic_search, read_child, read_parent]
triggers: [实验复现, 数据泄漏, 对照公平, 消融, 失败案例]
not-triggers: [临床诊断, 伦理审查结论, 未提供实验细节的论文]
outputs: [checklist, evidence, domain_caveats, unresolved]
failure_behavior: 检查项无证据时标记 UNKNOWN，不推断实验未执行。
---

# 实验公平性复核

## 适用场景

资料包含实验设计、训练配置、评测结果或失败分析，用户希望检查可比性与潜在偏差。

## 操作步骤

1. 建立检查清单：数据来源、划分、基线、评价指标、随机种子、计算预算、失败案例。
2. 用原文证据逐项填写 YES / NO / UNKNOWN；缺失报告记为 UNKNOWN，不记为 NO。
3. 检查测试集是否参与调参、是否存在同文档家族泄漏、基线是否使用相同预算。
4. 对非计算机领域（如临床）明确说明分级框架不适用，交由领域专家。
5. 输出未解决问题与需要补充的材料。

## 输出契约

- `checklist`：检查项、状态、证据。
- `domain_caveats`：领域限制。
- `unresolved`：无法从现有资料判断的事项。

## 反例

- 把“未报告随机种子”直接判为造假。
- 把一次 smoke test 写成泛化实验结论。
