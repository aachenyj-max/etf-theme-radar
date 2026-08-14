# 数据字典

## ETF 市场快照与证据进度

- `tool_calls.evidence_delta`：单次工具调用去重后新增入库的原始证据数。
- `tool_calls.relevant_evidence_delta`：其中治理后归属于当前研究主题的有效证据数。
- `tool_calls.coverage_before_json` / `coverage_after_json`：工具调用前后的确定性主题覆盖。
- 报告 `detail.landscape.market_snapshot`：旧报告兼容字段；读取时标记为 `legacy_report_snapshot`。
- `etf_market_snapshots`：独立 ETF 现状，包含 `snapshot_id`、`report_id`、`collected_at`、`market_as_of`、状态、逐 ticker 产品、错误摘要和完整 payload。`source_status` 记录天天基金/yfinance 各自状态，产品 `sources`、`field_provenance` 与 `cross_source_validation` 记录来源、日期和 `single_source`/`consistent`/`not_comparable` 状态；`reason_code` 区分 `product_identity_mismatch`、`date_mismatch`、`field_mismatch` 与 `no_comparable_fields`。刷新不改变报告版本；产品为空时存储入口返回 `False` 且不新增记录。
- `etf_preview_snapshots`：天天基金 ETF 预览不可变快照，保存三类产品、分类数量、源错误、采集/净值日期、计算方法和字段级来源 URL。总产品数为零时存储入口返回 `False`；读取只返回最后一次非空快照。
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
| `agent_goals` | 三 Agent 共用的持久目标；保存幂等键、类型、lane、状态/阶段、优先级、输入/结果、取消标志、deadline、lease、heartbeat 和 attempt。 |
| `agent_events` | Goal 的只追加安全审计事件；保存前后状态、事件类型、时间、安全摘要和结构化详情，不保存隐藏思维链。 |
| `concurrency_leases` | 单 Worker 内交互/后台并发槽占用；以 Goal 唯一绑定 owner、lane、获取时间、heartbeat 和过期时间。 |
| `conversations` | 研究对话元数据；保存所属用户、已选主题、标题、状态及创建/更新时间。 |
| `conversation_messages` | 不可变消息；按 `conversation_id + message_seq` 连续排序，以 `conversation_id + idempotency_key` 去重，并关联唯一 `research_turn` Goal；数据库触发器拒绝 UPDATE/DELETE。 |
| `content_quality_results` | 每个 evidence ID 的确定性完整性快照；保存内容哈希、解析版本、状态、缺失字段、问题码、正文/摘要/噪声指标和评估时间。 |
| `extracted_facts` | 每个 evidence ID 的当前结构化事实；保存内容哈希、解析版本、审计状态、主体、发生时间、动作、原文数字、领域、地点、产业链位置、逐条错误和抽取时间。 |
| `extraction_exceptions` | 历史重抽取异常队列；按 evidence ID、组合解析版本和阶段唯一，保存内容哈希、open/resolved、错误、尝试次数、首次/最近失败及解决时间。 |
| `independent_score_snapshots` | 每次研究运行按 `snapshot_scope` 保存主题可信度、产业动量和 ETF 机会度三条不可变记录；字段包含独立 `value`、`assessed/not_assessed`、`as_of_date`、输入覆盖率、配置版本、原因和组件，不含综合分。 |
| `etf_market_snapshots` | 保存报告旁的独立动态 ETF 行情快照及 stale-if-error 状态。 |
| `etf_preview_snapshots` | 保存天天基金产品目录、费率、规模、复权收益、申购状态及场内溢价/成交额的独立快照。 |
| `report_assets` / `report_versions` | 每个已确认主题保存一条主报告资产及其经用户核实的不可变版本；版本 payload 冻结 `conclusion`、`report_sections`、审计和引用。 |
| `theme_candidates` | 保存候选名称、状态、稳定签名、发现窗口、门槛指标和结构化视图。 |
| `candidate_evidence` / `candidate_entities` / `candidate_aliases` | 保存候选与证据、实体和临时别名的可追溯关系。 |
| `discovery_runs` / `source_watermarks` | 保存发现运行审计与来源增量游标；游标不替代原始来源 URL。 |

任务 2.1 契约共 40 张应用表，公共契约为 `2026-08-14.v13`。治理衍生表均保留对原始 evidence、主题或运行范围的引用；`rejected`、`incomplete`、异常队列、`not_comparable` 与 `not_assessed` 都是可审计状态，不等于删除或零值。

当前已增加 `agent_runs` 和扩展后的 `tool_calls`，用于记录模型、prompt 哈希、token、停止原因、工具参数/结果摘要、重试、延迟与证据增量。后续迁移仍需增加：`source_items`、`entities`、`entity_aliases`、`entity_links`、`theme_aliases`、`theme_events`、`etfs`、`etf_filings`、`etf_holdings`、`indexes`、`securities`、`security_theme_exposure`、`patents`、`papers`、`job_postings`、`social_posts`、`forum_posts`、`index_methodologies`、`model_runs` 与 `human_feedback`。

Agent Goal 状态转换由 Store 白名单控制：信息 Goal 使用 `queued → planning → collecting/extracting → validating → replanning（可选） → completed/partial/needs_attention`；排队取消直接进入 `cancelled`，活动取消先置 `cancel_requested`，再由 lease owner 确认终止。过期活动 lease 可被新 owner 原阶段恢复，`attempt` 增加且追加 `recovered` 事件。

研究消息写入与对应 Goal 创建位于同一 `BEGIN IMMEDIATE` 事务。`research_turn` 从 `queued` 首次领取后进入 `context_building`；领取查询排除已有同一 `conversation_id` 活跃 lease 的候选，但仍可领取其他对话。幂等重放返回原消息和原 Goal，不增加序号、不覆盖内容。

内容质量状态固定为 `publishable`、`needs_enrichment`、`rejected`。缺失字段包括 `raw_text`、`title`、`summary`、`distinct_summary`、`event_subject`、`event_action` 与 `clean_body`；对应问题码用于审计和重抽取路由。没有质量记录不等于通过。

结构化事实状态为 `audited` 或 `incomplete`。`numbers_json` 只保存冻结原文逐字出现的数字 token；`domain` 与 `industry_chain_position` 无明确证据时为 `unknown`，`occurred_at`、`subject`、`action`、`location` 无明确值时为空字符串。模型输出审计使用 evidence ID 隔离错误项。

历史重抽取结果中的 `effective_increment` 仅统计此前非 publishable、重抽取后变为 publishable 的 evidence；`recovery_point` 是本批最后检查的 event ID。异常状态只允许 `open`、`resolved`，重复失败增加 `attempt` 而不创建重复异常。

所有关键表应在适用时包含 `created_at`、`updated_at`、`source`、`provenance`、`parser_version`、`confidence` 和 `content_hash`，避免无法解释的结论或未来数据泄漏。

`report_sections` 固定包含 `why_theme`、`industry_chain`、`growth_drivers`、`etf_investment_angle`、`risks`、`scenarios`、`scorecard` 和 `evidence_gaps`。`evidence_gaps` 每项必须包含 `area`、`gap`、`why_missing`、`impact`、`next_action` 和 `status`；`scorecard.stars` 为 1–5 的正向评价，无法可靠评估时为 `NULL` 且 `status=not_assessed`。

ETF 预览统一字段：`operating_fee=management_fee+custody_fee`，单位为年化百分比；`scale_billion` 单位亿元；`return_2025` 为2025自然年度复权累计净值涨幅；`rolling_1y` 为截至最新有效净值日向前一年涨幅；`yesterday_return` 为最新公布的单日净值涨幅。`premium_rate=(同日收盘价/同日单位净值-1)×100%`，缺少同日值时必须为 `NULL`；`average_turnover_billion_20d` 为最多20个可用交易日的平均成交额，单位亿元。

美股主动分类证据保存在 `classification_evidence`。`name_or_profile` 表示基金名称或概况明确指向美国；`latest_top10_us_majority` 记录 `holdings_as_of`、美股/全部持仓数量及披露权重、`us_share`，门槛来自 `config/etf-preview.json`，当前为至少5只美股且美股占前十大披露权重不低于50%。

## 阶段 0 数据质量基准 fixture

以下样本仅用于离线回归，域名、发行人、产品名称和正文均已脱敏；它们记录已知输入缺陷或失败边界，不代表真实持仓、行情或来源状态：

| Fixture | 冻结问题 | 回归用途 |
|---|---|---|
| `tests/fixtures/title_equals_summary.json` | 标题被原样写入摘要，缺少事件主体、动作和事实正文 | 阶段 1 完整性门与历史重抽取输入 |
| `tests/fixtures/holdings_navigation_noise.html` | HTML 持仓页的导航、页脚与真实持仓表混在同一正文 | 阶段 1 持仓正文抽取与导航噪声过滤 |
| `tests/fixtures/etf_rate_limits.json` | AIQ、WTAI 分别返回脱敏 429 / rate-limit 错误 | 验证逐 ticker 失败隔离、冷却和最后成功缓存 |
| `tests/fixtures/empty_etf_snapshot.json` | 天天基金网与 yfinance 均无可用产品 | 验证空结果拒写且不覆盖最后成功快照 |

`title_equals_summary` 与持仓导航污染在本阶段只做基线冻结，不宣称质量问题已修复。ETF 失败样本则继续验证现有安全边界：单 ticker 失败不阻断其他产品，两源均空时研究运行失败并保留最后成功快照。
