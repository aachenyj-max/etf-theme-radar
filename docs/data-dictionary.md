# 数据字典

## ETF 市场快照与证据进度

- `tool_calls.evidence_delta`：单次工具调用去重后新增入库的原始证据数。
- `tool_calls.relevant_evidence_delta`：其中治理后归属于当前研究主题的有效证据数。
- `tool_calls.coverage_before_json` / `coverage_after_json`：工具调用前后的确定性主题覆盖。
- 报告 `detail.landscape.market_snapshot`：旧报告兼容字段；读取时标记为 `legacy_report_snapshot`。
- `etf_market_snapshots`：独立 ETF 现状，包含 `snapshot_id`、`report_id`、`collected_at`、`market_as_of`、状态、逐 ticker 产品、错误摘要和完整 payload。刷新不改变报告版本。
- `research_runs.queue_position`：等待任务的位置；活动任务和历史任务为 `NULL`。
- `buyer_count_status` 固定为 `not_available`；`fund_flow_status` 在没有可靠官方资金流来源时为 `not_assessed`。

| 数据表 | 用途 |
|---|---|
| `raw_documents` | 保存允许留存的原始公开证据、URL、访问说明与内容哈希。 |
| `normalized_events` | 保存结构化事件、主题/实体、来源质量与抽取置信度。 |
| `connector_health` | 记录来源可用性、启用状态和覆盖范围限制。 |
| `themes` / `theme_scores` | 保存演进式主题本体和时点评分分项。 |
| `citations` | 建立结论、事件与原始证据之间的引用关系。 |
| `product_proposals` | 保存仅供人工复核的产品草案。 |
| `research_runs` | 保存活动、等待和历史任务；状态、阶段、进度、lease 与队列位置均持久化。 |
| `etf_market_snapshots` | 保存报告旁的独立动态 ETF 行情快照及 stale-if-error 状态。 |

当前已增加 `agent_runs` 和扩展后的 `tool_calls`，用于记录模型、prompt 哈希、token、停止原因、工具参数/结果摘要、重试、延迟与证据增量。后续迁移仍需增加：`source_items`、`entities`、`entity_aliases`、`entity_links`、`theme_aliases`、`theme_events`、`etfs`、`etf_filings`、`etf_holdings`、`indexes`、`securities`、`security_theme_exposure`、`patents`、`papers`、`job_postings`、`social_posts`、`forum_posts`、`index_methodologies`、`model_runs` 与 `human_feedback`。

所有关键表应在适用时包含 `created_at`、`updated_at`、`source`、`provenance`、`parser_version`、`confidence` 和 `content_hash`，避免无法解释的结论或未来数据泄漏。
