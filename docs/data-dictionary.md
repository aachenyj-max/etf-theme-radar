# 数据字典

## ETF 市场快照与证据进度

- `tool_calls.evidence_delta`：单次工具调用去重后新增入库的原始证据数。
- `tool_calls.relevant_evidence_delta`：其中治理后归属于当前研究主题的有效证据数。
- `tool_calls.coverage_before_json` / `coverage_after_json`：工具调用前后的确定性主题覆盖。
- 报告 `detail.landscape.market_snapshot`：旧报告兼容字段；读取时标记为 `legacy_report_snapshot`。
- `etf_market_snapshots`：独立 ETF 现状，包含 `snapshot_id`、`report_id`、`collected_at`、`market_as_of`、状态、逐 ticker 产品、错误摘要和完整 payload。`source_status` 记录天天基金/yfinance 各自状态，产品 `sources`、`field_provenance` 与 `cross_source_validation` 记录来源、日期、单源/一致/冲突状态。刷新不改变报告版本；两源均空时不新增记录。
- `etf_preview_snapshots`：天天基金 ETF 预览不可变快照，保存三类产品、分类数量、源错误、采集/净值日期、计算方法和字段级来源 URL。读取时只返回最新快照。
- `detail.landscape.theme_etf_snapshot`：报告版本内冻结的主题相关 ETF 预览子集，包含原预览 `snapshot_id`、行情日期、匹配词、匹配字段、相关性分和产品字段；只允许确定性名称/别名/跟踪指数匹配。
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
| `etf_preview_snapshots` | 保存天天基金产品目录、费率、规模、复权收益、申购状态及场内溢价/成交额的独立快照。 |
| `report_assets` / `report_versions` | 每个已确认主题保存一条主报告资产及其经用户核实的不可变版本；版本 payload 冻结 `conclusion`、`report_sections`、审计和引用。 |
| `theme_candidates` | 保存候选名称、状态、稳定签名、发现窗口、门槛指标和结构化视图。 |
| `candidate_evidence` / `candidate_entities` / `candidate_aliases` | 保存候选与证据、实体和临时别名的可追溯关系。 |
| `discovery_runs` / `source_watermarks` | 保存发现运行审计与来源增量游标；游标不替代原始来源 URL。 |

当前已增加 `agent_runs` 和扩展后的 `tool_calls`，用于记录模型、prompt 哈希、token、停止原因、工具参数/结果摘要、重试、延迟与证据增量。后续迁移仍需增加：`source_items`、`entities`、`entity_aliases`、`entity_links`、`theme_aliases`、`theme_events`、`etfs`、`etf_filings`、`etf_holdings`、`indexes`、`securities`、`security_theme_exposure`、`patents`、`papers`、`job_postings`、`social_posts`、`forum_posts`、`index_methodologies`、`model_runs` 与 `human_feedback`。

所有关键表应在适用时包含 `created_at`、`updated_at`、`source`、`provenance`、`parser_version`、`confidence` 和 `content_hash`，避免无法解释的结论或未来数据泄漏。

`report_sections` 固定包含 `why_theme`、`industry_chain`、`growth_drivers`、`etf_investment_angle`、`risks`、`scenarios`、`scorecard` 和 `evidence_gaps`。`evidence_gaps` 每项必须包含 `area`、`gap`、`why_missing`、`impact`、`next_action` 和 `status`；`scorecard.stars` 为 1–5 的正向评价，无法可靠评估时为 `NULL` 且 `status=not_assessed`。

ETF 预览统一字段：`operating_fee=management_fee+custody_fee`，单位为年化百分比；`scale_billion` 单位亿元；`return_2025` 为2025自然年度复权累计净值涨幅；`rolling_1y` 为截至最新有效净值日向前一年涨幅；`yesterday_return` 为最新公布的单日净值涨幅。`premium_rate=(同日收盘价/同日单位净值-1)×100%`，缺少同日值时必须为 `NULL`；`average_turnover_billion_20d` 为最多20个可用交易日的平均成交额，单位亿元。

美股主动分类证据保存在 `classification_evidence`。`name_or_profile` 表示基金名称或概况明确指向美国；`latest_top10_us_majority` 记录 `holdings_as_of`、美股/全部持仓数量及披露权重、`us_share`，门槛来自 `config/etf-preview.json`，当前为至少5只美股且美股占前十大披露权重不低于50%。
