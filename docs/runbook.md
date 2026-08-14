# 运行手册与限制

启用 SEC 数据获取前，必须将 `SEC_USER_AGENT` 设置为包含联系信息的值。不得降低限速、规避访问限制或使用未授权凭据。数据源异常时，请检查 `connector_health` 和 pipeline 错误记录；其他来源应继续运行，同时相应降低结论置信度。

主题研究的确定性演示仍使用 fixture；示例中的标识、分数和事件不能被当作实时信号、真实持仓、AUM、SEC 状态或回测结果。ETF 预览另有真实公开数据同步，页面与 API 必须明确显示天天基金来源、采集时间和净值/行情日期。

## 研究运行实时流

研究工作台默认连接 `/api/research-runs/{run_id}/stream` 获取 SSE 审计快照。正常情况下会实时显示阶段和工具调用；浏览器或代理中断流式连接时自动回退到 2 秒轮询，并每 10 秒尝试恢复 SSE。等待人工复核或任务进入终态时连接会正常关闭。该信息流只包含持久化审计记录，不包含模型隐藏思维链。

证据进度包含两个口径：`raw_added` 是去重后写入证据库的新记录，`relevant_added` 是确定性治理后归属于当前主题的有效新增。两者不一致是正常现象，前端会展示基线、当前值和两个增量。

任务队列包含一个执行槽、FIFO 多任务等待队列和独立人工处理区，优先级依次为进行中、等待中、需要处理。`awaiting_*`、`returned` 与 `blocked_configuration` 不占执行槽；执行任务进入人工处理或终态时，最早等待项会在同一 SQLite 事务中自动提升。主题审核通过与退回任务重跑先进入等待队列；`returned` 也可调用 `POST /api/research-runs/{run_id}/finish` 结束。使用 `GET /api/research-runs` 检查 `queue_position` 与 `needs_attention`。

研究执行期间优先订阅 `GET /api/research-runs/{run_id}/stream`。SSE 每次工具开始、结束、证据增量和阶段变化都会发送新的持久化快照；单个慢来源仍在运行时会显示“运行中”，不需要等待最终报告。SSE 断开后前端回退到有限状态轮询。流中不包含模型隐藏思维链，最终报告只在审计完成后冻结。

## 主题发现与复核

来源同步任务由独立持久 `SyncDiscoveryWorker` 领取；每日首次启动使用 `daily:YYYY-MM-DD` 幂等键补采，手动 `POST /api/sync-runs` 只入队，不创建临时线程。同步完成后自动对最近 30 日未归类证据执行确定性聚类。门槛来自 `config/defaults.yaml` 的 `theme_discovery`，不得在前端或模型提示词中另设口径。

通过 `GET /api/theme-candidates` 检查候选及四类证据视图。`signal` 和 `validating` 仅用于观察；达到确认门槛后仍须人工调用 `POST /api/theme-candidates/{candidate_id}/review` 执行 `confirm`、`merge` 或 `reject`。三种动作均为 SQLite 原子事务，终态不会被后续发现覆盖。ETF 无可靠覆盖时显示 `not_assessed`，不得用缺失 ETF 证据否定主题。

若主题候选接口返回 404/405，说明 8001 仍运行旧契约进程。关闭旧启动窗口或对应的本项目服务后重新启动；v5 启动器不会复用缺少候选主题路由的旧服务。

## DeepSeek Agent 配置

复制 `.env.example` 为本地 `.env`，设置新的 `DEEPSEEK_API_KEY`。默认由 `deepseek-v4-flash` 执行阶段内工具选择，由 `deepseek-v4-pro` 执行主题定义与最终证据分析。旧的 `deepseek-chat`、`deepseek-reasoner` 名称不再使用。

Agent 只能调用注册的公开来源工具。统一主题研究默认最多 6 次模型请求、12 次工具调用和 480 秒，自动同时覆盖产业动量与 ETF 格局；来源优先级为现有证据/缓存、官方 ETF 持仓、天天基金快照、yfinance，再按缺口补学术、招聘、专利线索和反方检索。默认值位于 `config/defaults.yaml`。未配置 key 时流程使用确定性离线路径；401、模型不存在等配置错误会进入 `blocked_configuration`。

通过固定 API `http://127.0.0.1:8001/api/capabilities` 检查服务身份、契约版本、Worker 心跳、`7/8` 来源覆盖、模型与工具注册状态；固定前端为 `http://127.0.0.1:3000`。当前契约 `2026-08-14.v14` 在 `llm.concurrency` 中报告总上限 12、交互/后台预留 10/2、最低并发 2 和冷却 30 秒。通过 `GET /api/research-runs/{run_id}` 查看旧研究运行审计，通过对话消息返回的 `goal.goal_id` 检查新交互 Goal。响应不会包含 API key 或模型隐藏推理内容。

新入库事件的完整性结果可在 SQLite `content_quality_results` 中按 `event_id` 检查。首页证据数突然下降时，先按 `status`、`missing_fields_json` 和 `issues_json` 汇总，不要删除原始事件或手工改成 `publishable`。`needs_enrichment` 等待重抽取，`rejected` 仍保留原始文档用于审计；`config/defaults.yaml` 的 `maximum_boilerplate_ratio` 默认 0.25。

结构化事实保存在 `extracted_facts`，当前解析版本为 `fact-extraction-v1`。诊断摘要或事实缺失时同时核对 `content_hash`、`status` 与 `audit_errors_json`；数字必须回到对应 `raw_documents.text` 逐字复核。不要直接编辑事实行，历史数据由任务 1.4 的幂等回填工具处理。

历史回填必须先复制数据库并在复制品执行：

```powershell
python -m etf_theme_radar.cli backfill-evidence-extractions --db data/radar-copy.db --limit 500
python -m etf_theme_radar.cli backfill-evidence-extractions --db data/radar-copy.db --apply --limit 500
python -m etf_theme_radar.cli backfill-evidence-extractions --db data/radar-copy.db --apply --limit 500 --resume-after <recovery_point>
```

核对 `processed`、`effective_increment`、`failure_reasons`、`recovery_point` 和 `has_more`，并确认 `raw_documents` 行数/内容哈希未变化。`extraction_exceptions` 的 open 项必须查明缺失原文或写入错误；补齐后从合适恢复点重跑，成功项会变为 resolved。正式库仅在备份完成的维护窗口执行。

Agent Goal 的执行状态保存在 SQLite：`agent_goals` 是当前快照，`agent_events` 是只追加安全审计，`concurrency_leases` 是可过期槽位。遇到 429/503 时本地有效并发减半，冷却后逐槽恢复；不要通过增加 API/Worker 实例规避限速。Worker 重启后等待 lease 过期即可由新 owner 恢复，禁止人工直接改表抢占仍有效的 lease。

## 多对话消息与顺序诊断

使用 `POST /api/conversations` 创建绑定已选主题的研究对话；使用 `POST /api/conversations/{conversation_id}/messages` 写入用户消息，请求体必须包含客户端稳定的 `idempotency_key`。网络重试使用同一键会返回原消息和原 Goal（HTTP 200）；首次写入返回 HTTP 202。通过 `GET /api/conversations/{conversation_id}/messages` 按 `message_seq` 核对历史。不要直接更新或删除 `conversation_messages`，数据库会以 `conversation_messages are immutable` 拒绝操作。

若同一对话的后续消息长期 queued，先检查该对话前一 Goal 对应的 `concurrency_leases.expires_at` 和 owner；有效 lease 存在时属于正常串行等待。其他对话仍应能领取交互槽，若全部对话均停滞，再检查交互 lane 是否已达到 `/api/capabilities` 报告的上限。任务 2.1 发布检查为 40 张应用表、契约 `2026-08-14.v13`，并运行 `python -m pytest tests/test_conversations.py tests/test_research_queue.py -q`。

上下文权限异常时，先检查记忆/知识项的 `owner_user_id`、`allowed_user_ids`，以及关联摘要的 `conversation_id` 是否出现在当前对话显式允许集合中。构建审计只应显示各层拒绝数量，不能记录被拒绝内容。若关键消息未进入上下文，检查该项 `token_count`、总 `token_budget` 和 `truncated_layers`；高信任层被截断后低信任层保持空白是预期行为。任务 2.2 回归命令为 `python -m pytest tests/test_context_builder.py tests/test_ontology_and_security.py -q`。

三响应模式诊断：`answer_now` 出现工具调用表示路由或调用方越界；`quick_retrieve` 的 `retrieval_sources` 最多 3 项，必须因证据充分、来源检查完成或快速预算耗尽停止；`background_research` 响应应先包含 `phase_answer_ready`，随后为 `background_goal_created`。重复同一消息序号时检查是否复用 `background_research:{conversation_id}:{message_seq}`。若回答被拒绝，核对 citations 是否都存在于冻结证据或本轮工具结果。任务 2.3 回归命令为 `python -m pytest tests/test_research_agent_modes.py tests/test_research_workflow.py tests/test_research_quality.py -q`。

对话实时事件优先订阅 `GET /api/conversations/{conversation_id}/stream?after_event_id=<last>`；SSE 中断后使用 `GET /api/conversations/{conversation_id}/events?after_event_id=<last>` 轮询，再以返回的 `last_event_id` 续传。若出现重复事件，检查客户端是否错误重置游标；若缺事件，直接核对 `agent_events` 是否先持久化。工具事件只应包含安全摘要和两类证据增量。任务 2.4 回归包括 API 契约、`tests/test_conversations.py` 与 `frontend/e2e/research-review.spec.ts`。

研究完成后可按 `theme_id` 和运行 ID 在 `independent_score_snapshots` 核对三条评分。`not_assessed` 表示来源类型、历史快照或已核验 ETF 数量未达到配置门槛；不得手工补零、将旧主题强度当综合分，或跨三个维度自行加权。公式、门槛与 `independent-scores-v1` 版本均来自 `config/defaults.yaml`。

阶段 1 发布前检查：契约导出应为 38 张应用表和 `2026-08-14.v12`；全量 pytest 必须通过；抽样确认 Agent lease 可恢复、质量失败不进入正式研究、历史回填不改原文、ETF 空结果不覆盖缓存，以及每个研究运行恰有三个独立评分维度。任一项失败都不得进入后续阶段。

所有产品材料仅为内部研究草案。使用前必须经过基金法务、合规、指数、AP/做市商和交易所上市团队复核。系统不提供投资、法律、税务或合规意见，也不执行任何交易。

## ETF 市场快照

主题报告可通过 `POST /api/reports/{report_id}/market-snapshot` 创建持久双源刷新任务。Worker 读取报告冻结的 ETF 候选和天天基金主题子快照，再逐 ticker 调用 yfinance；任务只写入独立 `etf_market_snapshots`，不改变报告版本、正文哈希或结论。请求按 ticker 节流，对 429 按 `refresh_retry_attempts` 与 `refresh_retry_backoff_seconds` 有限退避并记录冷却；逐产品和逐来源错误分别保存。两源均无有效产品时任务失败且不写新快照，最后成功快照继续可读。

双源核验不是强制要求所有字段在两个来源都存在。只有产品身份、日期和字段口径均可比且值一致时才返回 `consistent`。ISIN 冲突拆为两个 `single_source` 产品；跨日期、同日字段值冲突或没有共同口径字段时返回 `not_comparable` 并记录原因码。`field_provenance`、`sources` 和 `source_status` 保留来源、日期、URL、失败原因及缓存状态。单 ticker 冷却即使没有成功缓存也会跳过重复请求；市场与预览空快照由存储层拒绝。成交活跃度不代表买入人数或资金流。

报告发布前检查 `audit.publication_gate`。核心结论、产业链、增长驱动力、ETF 角度、风险、三种情景、七项评分、证据缺口解释、有效 claim-evidence 引用、反方检查和 ETF 字段来源均通过后，用户才能确认发布。失败时只能要求补充研究，不能提升主报告版本。

## ETF 预览同步

每个工作日北京时间 08:00，`SyncDiscoveryWorker` 会以日期幂等键排队一次天天基金同步。手动调用 `POST /api/etf-preview/refresh` 只创建或复用任务，前端不得因网络错误自动重放。通过 `GET /api/sync-runs/{sync_run_id}` 查看进度，通过 `GET /api/etf-preview` 读取最后一次成功快照；同步失败不会用空数据覆盖旧快照。

本地诊断命令：

```powershell
python -m etf_theme_radar.cli etf-preview-sync --db data/radar.db
python -m etf_theme_radar.cli etf-preview-audit --db data/radar.db
```

公开页面缓存位于 `data/cache/tiantian-etf-preview`。动态数据默认缓存30分钟，基金档案缓存6小时；逐基金请求限速且不得绕过验证码、登录或访问限制。溢价审计必须同时检查 `market_date`、`market_price`、`same_day_nav` 和 `premium_source`。跨境基金净值滞后是正常现象，系统改用对应净值日的历史收盘价，不允许用最新价格除以前一日净值。

## 故障排查

- `SEC_USER_AGENT is required`：在本地 `.env` 中设置联系人型 User-Agent，且不要提交该文件。
- Connector 状态为 `disabled`：检查环境变量中的开关；关闭可选来源不应影响 fixture 或其他来源。
- 外部请求失败：保留错误记录，使用缓存或 fixture 验证流程，不得伪造抓取结果。
- ETF 行情刷新长期排队：检查是否存在 `report-refresh:*` 任务和 Worker heartbeat；刷新任务应在当前阶段释放 lease 后优先领取。单次最多 6 只、逐 ticker 8 秒，空响应记为失败；报告详情表会显示逐只错误，只有非空的历史缓存才能作为 stale 快照回退。
- `blocked_configuration`：检查 key、账户权限、`LLM_BASE_URL` 和 V4 模型名，修复后重新运行任务。
- Agent Goal 长期停留在活动状态：检查 `lease_expires_at`、`heartbeat_at`、对应 `concurrency_leases.owner` 和 Worker 心跳；只有 lease 已过期才应由重启 Worker 恢复。执行中取消是协作式的，会在下一个安全边界变为 `cancelled`。
- 首页证据为 0 但数据库有事件：检查这些事件是否缺少 `content_quality_results`，或因 `title_equals_summary`、`empty_body`、`boilerplate_ratio_exceeded`、`missing_event_subject`、`missing_event_action` 未通过；不要将未知历史记录默认放行。
- 冷启动超过 90 秒：v6 启动器会继续等待到 180 秒；若仍失败，读取 `data/logs/api-error.log` 与 `frontend-error.log`，不得改用其他端口绕过。
## 历史证据摘要升级

先使用 dry-run 查看仍包含旧固定模板的报告：

```powershell
python -m etf_theme_radar.cli backfill-evidence-summaries --db data/radar.db
```

确认后显式增加 `--apply`。升级会追加不可变报告版本并原子提升资产指针，不修改旧版本；重复执行保持幂等。命令只使用报告中已经冻结的证据，不重新访问来源网页。失败报告会保留原版本并在 JSON 结果的 `failed` 中列出。
