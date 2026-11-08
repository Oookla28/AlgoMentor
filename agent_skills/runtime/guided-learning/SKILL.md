---
name: guided-learning
version: 1.0.0
description: 从已有资料生成可核验的学习提纲、分层提示与一次自测，不更新正式掌握度。
allowed-tools: [keyword_search, semantic_search, read_child, read_parent]
triggers: [学习目标, 提纲, 提示, 自测]
not-triggers: [正式判题, 修改成绩, 掌握度写入]
outputs: [outline, hints, self_check, source_links, unverified_notes]
failure_behavior: 仅输出有证据的提纲；练习生成失败不阻断资料阅读。
---

# 引导式学习

## 适用场景

学习者给出目标（例如“理解循环队列判满与判空”），希望从自己的资料生成学习路径。

## 操作步骤

1. 将目标拆成 2–4 个可核验子目标，每个子目标必须能映射到资料片段。
2. 按“先定义、再条件、后例子”的顺序生成提纲。
3. 为每个子目标提供一个不直接给答案的提示。
4. 构造一道自测题，明确标注“自动构造，非正式题库”。
5. 始终把 AI 反馈与客观判题成绩分开；本 Skill 不写入 BKT 或课程分数。

## 输出契约

- `outline`：层级标题 + 对应证据链接。
- `hints`：每层一个提示，禁止伪造学生已掌握。
- `self_check`：题干、参考要点、来源；不宣称官方评分。
- `unverified_notes`：缺少资料或无法生成的部分。

## 失败行为

资料不足时输出“当前空间缺少该主题资料”，而不是通用教材式臆测。

## 反例

- 自动把自测题加入正式题库。
- 根据聊天次数推断掌握度提升。
