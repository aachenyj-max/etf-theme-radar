# 架构说明

系统遵循以下数据流：

```text
持久同步 Worker → 数据连接器 → 原始证据库 → 标准化/治理事件 → 候选主题聚类 → 人工确认 → 正式主题 → 有界研究 Agent → Dashboard
```

每个连接器均为独立适配器，单一来源失败不应中止整个 pipeline。原始记录必须保留来源 URL、内容哈希、抓取时间、访问说明和解析版本，以确保任何研究结论可追溯至许可访问的公开证据。

Workflow 持有阶段、审批、取消、恢复、预算和最终状态；PydanticAI Agent 只在采集阶段选择注册工具、判断证据缺口并提交停止理由。模型不能直接执行 SQL、写文件、修改状态或决定确定性评分。`agent_runs` 保存模型、prompt 哈希、用量和停止原因，`tool_calls` 保存参数/结果摘要、延迟、重试和证据增量。隐藏思维链不持久化；中断后从证据账本和工具摘要开始新的 attempt。

三 Agent 共用的调度底座由 `agent_goals`、`agent_events` 与 `concurrency_leases` 构成。创建以 `idempotency_key` 去重；领取 Goal 与占用 lane 槽位在同一 `BEGIN IMMEDIATE` 事务内完成。普通 queued Goal 首次领取进入 planning，`research_turn` 首次领取进入 context_building；活动 Goal 的 lease 过期后由新 Worker 原阶段恢复并增加 attempt。领取交互 Goal 时会跳过已有未过期 lease 的同一 `conversation_id`，但继续选择其他对话，因此保证对话内串行而不把整个交互 lane 降为单槽。heartbeat 必须同时匹配 Goal 和并发 lease 的 owner。排队取消立即终止，执行中取消只设置持久标志并由 owner 在安全边界确认。安全事件只追加，不保存隐藏思维链。

`conversations` 保存用户、已选主题和对话状态；`conversation_messages` 以 `(conversation_id, message_seq)` 排序，并以 `(conversation_id, idempotency_key)` 去重。用户消息、连续序号与对应交互 Goal 在一个短写事务内生成，数据库触发器拒绝消息 UPDATE/DELETE，后续总结只能追加版本化资产，不能改写历史输入。

研究上下文构建器是纯确定性边界：先过滤私有记忆、跨对话摘要和知识片段的用户 ACL，再验证跨对话摘要是否位于当前对话的显式允许集合。通过权限门后，按主题定义、独立评分快照、压缩检查点、近期原始消息、已核验证据、冻结 ETF 快照、个人记忆、关联摘要、授权知识的顺序消费 token 预算。近期消息从最新序号向前保留，再恢复时间顺序；任一高信任层预算不足时停止选择后续低信任层。

研究响应路由不依赖模型自选：冻结上下文充分且无需最新数据时使用 `answer_now`；缺口不超过快速检索边界且存在直接来源时使用 `quick_retrieve`，最多去重选择 3 个来源，并在证据充分、来源全部检查或快速预算耗尽时停止；其余进入 `background_research`。后台模式把阶段性回答与缺口一起冻结在幂等 Goal payload 中，重复请求返回原回答/原 Goal。回答引用发布前取冻结 evidence ID 与本轮工具结果 ID 的并集校验，未知 ID 直接拒绝。

对话实时流复用 `agent_events` 的全局递增 `event_id`，不新增临时内存队列。写入接口只接受白名单安全字段；读取按所属用户和 `conversation_id` 过滤，再以 `after_event_id` 增量返回。SSE `/stream` 与 JSON `/events` 共用同一游标，因此断线后轮询或重连不会重复已确认事件。旧 `research_runs` 快照流继续兼容，前端迁移在阶段 2 后续任务完成。

总结任务复用后台 lane 的持久 `agent_goals`。每次回答把 `not_before_at` 推迟到最新防抖时间并合并 `target_message_seq`；Worker 到期后首次领取直接进入 `summarizing`。输出写入只追加的 `conversation_summary_versions` 与 `context_checkpoints` 前，必须验证数据库中的不可变消息副本、连续覆盖、source message、evidence ID 和上一版本。失败只返回 `rebuild_required`，不追加貌似完整的版本。`memories` 保存用户可控状态和版本，编辑/纠正创建新记录并以 `memory_relations.supersedes` 指向旧记录；正式研究资产不在该服务的写集合内。

`conversation_links` 是按源对话保存的显式允许集合，无记录即关闭。写入前一次性验证目标对话与源对话属于同一用户和同一主题，再在短事务中禁用旧集合并 upsert 新集合；验证失败不会改变原选择。关联检索联接目标对话的最新 `conversation_summary_versions`，返回摘要、关键词和覆盖范围，不联接 `conversation_messages`。上下文构建器仍执行第二层允许集合与用户 ACL 校验。

单 Worker 的本地 DeepSeek 并发默认上限为 12，交互 lane 预留 10，后台信息规划/总结 lane 预留 2。429/503 将有效上限减半但不低于 2，并确保两个 lane 各保留一个槽；冷却后每次只恢复一个槽。静态边界通过 `/api/capabilities` 暴露。

标准化事件在 ingest 事务中同步执行 `content-quality-v1` 完整性门。门只使用冻结原文和事件字段，检测空正文、标题式摘要、导航/页脚噪声比例、事件主体和动作；结果写入 `content_quality_results`。`publishable` 是首页证据、主题快照评分和正式研究选择的共同前置条件；`needs_enrichment` 与 `rejected` 继续保留原文和治理事件，供后续幂等重抽取，不以空成功覆盖。

同一事务随后运行 `fact-extraction-v1`，将主体、发生日期、动作、原文数字、主题领域、显式地点和产业链位置写入 `extracted_facts`。确定性结果缺少主体/动作时标记 `incomplete`，不推断未知项。模型增强接口先核对输出条目与输入 evidence ID 的一一对应，再逐项验证数字必须存在于该 ID 的冻结原文；单项失败只拒绝该项并保存审计原因。

历史重抽取从 `raw_documents` 与 `normalized_events` 只读构建质量/事实结果。`content_hash + content-quality-v1 + fact-extraction-v1` 均一致时跳过；批次按 event ID 排序并返回 `recovery_point`。缺失原文或写入异常追加/更新 `extraction_exceptions`，后续成功将同一异常置为 `resolved`。整个流程不写原始文档，也不改报告版本。

普通主题研究由 SQLite 原子队列限制为一个执行槽，并维护按 `queue_position` 排序的 FIFO 多任务等待队列。`awaiting_*`、`returned` 与 `blocked_configuration` 属于独立人工处理状态，不占执行槽；执行项进入人工处理或终态后，在同一写事务中提升最早等待项。主题审核通过和退回任务重跑先追加到等待队列，只有排到队首且执行槽空闲时才恢复对应阶段。Worker 重启时会先提升遗留等待项，且不会并行领取两个普通研究任务。

主题搜索在研究立项之前运行。`SyncDiscoveryWorker` 以 SQLite lease 串行领取来源同步任务，结束后对观察窗口内尚未分配的证据执行确定性词项/实体聚类。候选只在达到配置化可信度门槛后参与排序，状态依次为 `signal`、`validating`、`awaiting_confirmation`；人工确认或合并后才写入正式主题本体。DeepSeek 可在后续深研中解释证据与补缺口，但不能绕过此状态机。

不可变报告与动态 ETF 现状分离：每个已确认主题使用 `theme-report:{theme_id}` 维护一条规范主报告版本链，`report_versions` 保存冻结正文、结构化结论、产业链、三情景、评分、ETF 格局与 claim-evidence 引用；`etf_market_snapshots` 保存独立手动刷新行情。只有通过发布质量门槛并经用户核实的研究运行才能原子追加版本；报告详情可按 `version` 读取冻结版本，`timeline`/`compare` 返回结论、评分、ETF 和证据缺口的结构化变化。刷新不会改写报告资产或内容哈希。

ETF 动态数据由确定性双源工作流生成。天天基金网提供境内基金档案、费率、规模、净值收益与场内指标，yfinance 提供全球交易所行情和成交活跃度。二者覆盖不同市场，合并层要求产品身份、日期与字段口径同时可比：ISIN 冲突拆为两个 `single_source` 产品，跨日期或同日字段冲突标记 `not_comparable`，只有同日同口径一致值才可标记 `consistent`。所有单源字段保留 provenance。逐 ticker 失败隔离、缓存、退避和冷却由代码与 `config/defaults.yaml` 控制；冷却在没有成功缓存时也阻止重复请求。市场与预览存储入口均拒绝空产品快照，因此两源无可用新数据时不会覆盖最后成功值。

ETF 预览是独立采集的只读产品目录。`SyncDiscoveryWorker` 以 `etf-preview:daily:YYYY-MM-DD` 或 `etf-preview:manual:*` 幂等键领取采集任务，自动发现天天基金目录后先做确定性互斥分类，再逐基金读取公开档案、复权净值和交易状态。美股主动候选先排除明确的中国、港股、亚洲、日本、印度、越南、欧洲等地域产品；名称/概况未明确指向美国者，再用最新前十大持仓的市场代码与权重验证美国主要暴露。结果整批写入不可变 `etf_preview_snapshots`；单只基金失败被隔离，失败运行不会覆盖最后一次成功快照。主题报告在生成边界读取最新成功快照，按主题名称、确认别名和跟踪指数确定性匹配后将相关产品冻结进报告版本；不因美股/海外大类自动判定相关。场内产品的溢价使用同一日期的收盘价和单位净值，不能用不同日期数据或盘中估值替代。

现有连接器覆盖 SEC、OpenAlex、公开招聘、发行人 ETF 持仓、Yahoo Finance ETF 公开资讯及受控公开发现；来源按授权与可用性降级。ETF 信号不参与候选主题的最低成立条件，只在主题形成后描述可投资性与拥挤度，缺失时保持 `not_assessed`。

主题评分由配置与确定性代码共同驱动。只有在至少具备三类独立来源、其中一类为官方来源，且上市公司覆盖满足阈值时，主题才能获得高置信度。社交媒体与 Seeking Alpha 均为可选来源，默认关闭，不能单独支持产品发行结论。

## 2026-08-14 契约冻结基线

本节冻结阶段 0 / 任务 0.1 开始时的兼容面，不引入新业务行为。可运行 `python tools/export_contract_snapshot.py` 从临时 SQLite、FastAPI 路由表和 `frontend/src/services/*.ts` 重新导出机器可读 JSON，并用 `tests/test_api_contracts.py` 检查关键项。

### 服务身份与报告标识

- 服务 ID：`etf-theme-radar`。
- 阶段 0 冻结时公共契约版本为 `2026-08-05.v9`。任务 1.1 因 `/api/capabilities` 新增 `llm.concurrency` 提升为 v10；任务 1.2 因首页证据语义和质量表契约变化提升为 v11；任务 1.6 因研究结果增加三个独立评分快照提升为 v12；任务 2.1 因新增多对话与不可变消息路由提升为 v13；任务 2.4 因新增对话事件轮询与 SSE 路由提升为 v14；任务 2.6 因新增跨对话关联 GET/PUT 路由提升为 `2026-08-14.v15`。`/health` 与 `/api/capabilities` 必须报告相同版本。
- 新规范主题主报告使用 `theme-report:{theme_id}`。旧资产 `report:{run_id}` 仍是受支持标识；API 路由边界只解码一次，并通过 `run_registry` 定位独立运行数据库。`GET /api/reports/{report_id}/detail` 等报告路由不得将 `report:` 前缀改写成新标识。

### SQLite 表

当前应用表共 31 张；SQLite 内部的 `sqlite_*` 表不计入契约：

这是阶段 0 的冻结表面。任务 1.1 当前应用表增加至 34 张，新增 `agent_goals`、`agent_events`、`concurrency_leases`；原 31 张表保持兼容。

任务 1.2 当前应用表增加至 35 张，新增 `content_quality_results`；原表仍保持兼容。

任务 1.3 当前应用表增加至 36 张，新增 `extracted_facts`；公开 API 形状未变化，契约版本保持 `2026-08-14.v11`。

任务 1.4 当前应用表增加至 37 张，新增 `extraction_exceptions`；公开 API 形状未变化，契约版本保持 `2026-08-14.v11`。

任务 1.6 当前应用表增加至 38 张，新增 `independent_score_snapshots`；研究结果新增三个独立评分维度，契约版本提升为 `2026-08-14.v12`。三个维度仅共享主题和运行范围，不计算跨维度综合分。

任务 2.1 当前应用表增加至 40 张，新增 `conversations` 与 `conversation_messages`；公开契约提升为 `2026-08-14.v13`。旧 `research_runs` 单执行槽继续用于普通主题研究，新的 `research_turn` 使用交互 lane 并按 `conversation_id` 串行。

任务 2.5 当前应用表增加至 44 张，新增 `conversation_summary_versions`、`context_checkpoints`、`memories` 与 `memory_relations`。这些是内部持久运行时资产，公共契约保持 `2026-08-14.v14`。

任务 2.6 当前应用表增加至 45 张，新增 `conversation_links`；公开契约提升为 `2026-08-14.v15`。

阶段 1 的治理顺序固定为：持久 Goal 领取与 lease 隔离 → 原文完整性评估 → 逐条事实抽取审计 → 研究/刷新边界 → 独立评分持久化。历史回填复用同一质量与抽取函数，并以内容哈希、解析版本和恢复点保证幂等；任何下游报告都不能把未通过质量门、不可比 ETF 字段或 `not_assessed` 维度转换成肯定结论。

| 领域 | 表 |
|---|---|
| 原始证据与治理 | `raw_documents`、`normalized_events`、`citations`、`connector_health` |
| 主题与评分 | `themes`、`theme_aliases`、`theme_snapshots`、`theme_scores`、`independent_score_snapshots` |
| 候选发现 | `theme_candidates`、`candidate_evidence`、`candidate_entities`、`candidate_aliases`、`discovery_runs`、`source_watermarks` |
| 实体 | `entities`、`entity_aliases`、`entity_links` |
| 研究运行与审计 | `research_runs`、`run_registry`、`run_steps`、`approvals`、`agent_runs`、`tool_calls` |
| 报告与引用 | `report_assets`、`report_versions`、`report_claims`、`report_claim_evidence` |
| ETF 与同步 | `etf_market_snapshots`、`etf_preview_snapshots`、`sync_runs` |
| 旧兼容资产 | `product_proposals` |

状态列目前是 SQLite `TEXT`，没有数据库 `CHECK` 约束；下列集合由 API、Store、Worker 与确定性状态机控制：

| 状态域 | 当前值 |
|---|---|
| 普通研究执行槽 | `planning`、`queued`、`collecting`、`governing`、`analyzing`、`auditing` |
| 普通研究暂停/人工处理/终态 | `waiting`、`awaiting_theme_review`、`awaiting_report_review`、`returned`、`blocked_configuration`、`completed`、`cancelled`、`failed` |
| 主题候选 | `signal`、`validating`、`awaiting_confirmation`、`confirmed`、`merged`、`rejected` |
| 来源同步 | `queued`、`running`、`completed`、`cancelled`、`failed` |
| 发现运行 | `queued`、`running`、`completed`、`failed` |
| 报告资产 | `deep_research`、`watch`、`completed`、`draft`、`archived` |
| 主题定义 | `draft`、`confirmed` |
| 实体复核 | `pending`、`confirmed`、`rejected` |
| 连接器健康 | `healthy`、`degraded`、`disabled` |

队列兼容语义：同一 SQLite 数据库只允许一个普通研究执行项；其余任务按 `queue_position` FIFO 等待。执行项释放槽位与最早等待项提升位于同一事务。人工处理状态不占执行槽；审核通过或退回重跑先加入等待队列。列表顺序为执行中、等待中、需要处理、其他终态。

### FastAPI 路由

以下为应用路由表中的冻结清单，不含 FastAPI 自动生成的 OpenAPI/文档路由：

| 领域 | 方法与路径 |
|---|---|
| 健康与能力 | `GET /health`；`GET /api/capabilities`；`GET /api/connectors/health` |
| 认证 | `GET /api/auth/session`；`POST /api/auth/login`；`POST /api/auth/logout` |
| 研究对话 | `GET/POST /api/conversations`；`GET/POST /api/conversations/{conversation_id}/messages` |
| 对话审计 | `GET /api/conversations/{conversation_id}/events`；`GET /api/conversations/{conversation_id}/stream` |
| ETF 预览 | `GET /api/etf-preview`；`POST /api/etf-preview/refresh` |
| 采集同步 | `POST /api/pipeline/run`；`POST /api/sync`；`GET/POST /api/sync-runs`；`GET /api/sync-runs/{sync_run_id}`；`POST /api/sync-runs/{sync_run_id}/cancel` |
| 证据 | `GET /api/evidence`；`GET /api/evidence/facets`；`GET /api/evidence/{evidence_id}` |
| 主题与发现 | `GET /api/themes`；`GET /api/theme-candidates`；`GET /api/theme-candidates/{candidate_id}`；`POST /api/theme-candidates/{candidate_id}/review`；`GET /api/discovery-runs` |
| 实体 | `GET /api/entities/review`；`POST /api/entities/{entity_id}/review` |
| 首页与搜索 | `GET /api/dashboard`；`GET /api/search` |
| 报告库 | `POST /api/reports/daily`；`GET /api/reports`；`POST /api/reports/assistant`；`GET/PATCH/DELETE /api/reports/{report_id}` |
| 报告详情 | `GET /api/reports/{report_id}/detail`；`GET /api/reports/{report_id}/versions`；`GET /api/reports/{report_id}/timeline`；`GET /api/reports/{report_id}/compare`；`POST /api/reports/{report_id}/market-snapshot` |
| 统一主题研究 | `GET/POST /api/research-runs`；`GET /api/research-runs/{run_id}`；`GET /api/research-runs/{run_id}/stream`；`GET /api/research-runs/{run_id}/report`；`POST /api/research-runs/{run_id}/theme-review`；`POST /api/research-runs/{run_id}/report-review`；`POST /api/research-runs/{run_id}/rerun`；`POST /api/research-runs/{run_id}/cancel`；`POST /api/research-runs/{run_id}/finish` |
| 旧事件研究兼容 | `POST /api/event-research-runs`；`GET /api/event-research-runs/{run_id}`；`GET /api/event-research-runs/{run_id}/report` |

### 前端 gateway 依赖

| 文件 | API 依赖 |
|---|---|
| `evidence-explorer-gateway.ts` | `/api/evidence`、`/api/evidence/{evidence_id}` |
| `report-detail-gateway.ts` | `/api/reports/{report_id}/detail`、`/timeline`、`/compare`、`/market-snapshot` |
| `report-library-gateway.ts` | `/api/reports`、`/api/reports/{report_id}`、`/api/reports/assistant` |
| `research-workflow-gateway.ts` | `/api/research-runs`、`/api/research-runs/{run_id}`、`/stream`、`/cancel`、`/finish`、`/theme-review`、`/report-review`、`/rerun` |
| `theme-radar-gateway.ts` | `/api/themes`、`/api/theme-candidates/{candidate_id}/review` |

`app-shell.tsx`、`source-intelligence-wall.tsx`、`system-workspace.tsx` 等组件还直接读取 `/api/capabilities`、`/api/search` 和同步状态；这些属于现有组件依赖，不应被误认为可移除的未使用路由。
