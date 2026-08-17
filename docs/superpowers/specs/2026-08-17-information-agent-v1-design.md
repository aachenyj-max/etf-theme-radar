# 信息 Agent v1 设计

## 目标

实现阶段 3 / 任务 3.1：通过持久化后台 Goal 运行每日或事件信息规划循环；仅以治理后有效证据增量继续支持性采集，结束前必须记录反方检查和证据缺口。

## 边界

- 新增 `etf_theme_radar/info_agent.py` 和版本化提示词 `etf_theme_radar/prompts/info_agent.md`。
- 复用 `agent_goals`、`agent_events`、`concurrency_leases`、`agent_runs` 和 `tool_calls`；不新增 SQLite 表、公开 API 或服务契约。
- 只由 `SyncDiscoveryWorker` 领取和执行 `information_collection` 后台 Goal。`conversation_summary` 保持排队，留给其后续专用执行器。
- 仅处理 `information_kind` 为 `daily`、`event` 或 `background_research` 的 Goal；未知 Goal 类型安全失败，不执行外部采集。
- 不实施主题覆盖矩阵、每日简报资产/接口、候选主题状态机或前端变更。

## 运行模型

`create_information_goal` 以稳定幂等键创建后台 `information_collection` Goal。每日键为 `information:daily:<YYYY-MM-DD>`；事件键为 `information:event:<evidence_id>`；对话后台检索沿用已有键。

Worker 领取 Goal 后，以 `planning → collecting → counter_search → summarizing → completed` 进行持久状态转换。规划器先读取通过 `content_quality_results.publishable` 且治理后与目标相关的证据基线。每轮支持性采集后重新计算有效增量；达到配置的连续零有效增量上限后，停止支持性采集。无论停止原因如何，均执行一次受审计的反方检查，再生成缺口汇总和安全结果摘要。取消请求在阶段边界确认并转换为 `cancelled`。

模型仅可在正式提示词约束下选择已批准来源，不能写 SQL、改变主题终态或输出未验证事实。模型未配置时以确定性结果完成：保留缺口、反方检查状态和停止原因，绝不伪称已采集。

## 验证

先写 `tests/test_info_agent.py`：提示词版本化、每日/事件 Goal 幂等、治理有效增量停止、必经反方检查/缺口汇总、取消与 Worker 调度。现有 `tests/test_agent_runtime.py` 用于回归统一预算与已有研究 Agent 行为。

本任务按用户指示不在本对话运行测试。完成时提供：

`python -m pytest tests/test_info_agent.py tests/test_agent_runtime.py -q`

及必要的完整回归清单。任务在 `progress.md` 中保留未勾选，并明确代码待外部验证。
