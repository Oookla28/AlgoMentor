---
name: task-recovery
version: 1.0.0
description: 读取已有运行步骤，判断安全重试或续跑；避免重复外部副作用。
allowed-tools: [read_child, read_parent, read_siblings]
triggers: [任务恢复, 重试, 续跑, worker 重启]
not-triggers: [首次执行, 创建新任务]
outputs: [completed_steps, safe_to_retry, checkpoint, side_effect_status]
failure_behavior: 状态不明时停止并请求人工确认，不盲目重放。
---

# 任务恢复

## 适用场景

任务因 worker 退出、租约过期或用户取消而中断，需要继续或重试。

## 操作步骤

1. 读取 `AgentRun`、`AgentStep`、`Evidence` 与 `TaskArtifact`，确认已完成阶段。
2. 只读检索可安全重试；已发出的外部写操作状态不明时不得重复。
3. 续跑保留旧步骤，新增步骤从下一个编号开始；产物只追加，不覆盖已发布版本。
4. 重试创建新 run 或增加 attempt，重新计算权限与预算，不重置累计消耗。
5. 检查 `cancel_requested`；已取消任务不得被迟到结果复活。

## 输出契约

- `completed_steps`：已完成步骤摘要。
- `safe_to_retry`：布尔值与理由。
- `checkpoint`：可复用的证据 ID 与阶段。
- `side_effect_status`：NONE / KNOWN / UNKNOWN。

## 反例

- 对支付、发信等外部写操作盲目重试。
- 用旧 attempt 的结果覆盖新 attempt。
