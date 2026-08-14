# 架构说明

系统遵循以下数据流：

```text
持久同步 Worker → 数据连接器 → 原始证据库 → 标准化/治理事件 → 候选主题聚类 → 人工确认 → 正式主题 → 有界研究 Agent → Dashboard
```

每个连接器均为独立适配器，单一来源失败不应中止整个 pipeline。原始记录必须保留来源 URL、内容哈希、抓取时间、访问说明和解析版本，以确保任何研究结论可追溯至许可访问的公开证据。

Workflow 持有阶段、审批、取消、恢复、预算和最终状态；PydanticAI Agent 只在采集阶段选择注册工具、判断证据缺口并提交停止理由。模型不能直接执行 SQL、写文件、修改状态或决定确定性评分。`agent_runs` 保存模型、prompt 哈希、用量和停止原因，`tool_calls` 保存参数/结果摘要、延迟、重试和证据增量。隐藏思维链不持久化；中断后从证据账本和工具摘要开始新的 attempt。

普通主题研究由 SQLite 原子队列限制为一个执行槽，并维护按 `queue_position` 排序的 FIFO 多任务等待队列。`awaiting_*`、`returned` 与 `blocked_configuration` 属于独立人工处理状态，不占执行槽；执行项进入人工处理或终态后，在同一写事务中提升最早等待项。主题审核通过和退回任务重跑先追加到等待队列，只有排到队首且执行槽空闲时才恢复对应阶段。Worker 重启时会先提升遗留等待项，且不会并行领取两个普通研究任务。

主题搜索在研究立项之前运行。`SyncDiscoveryWorker` 以 SQLite lease 串行领取来源同步任务，结束后对观察窗口内尚未分配的证据执行确定性词项/实体聚类。候选只在达到配置化可信度门槛后参与排序，状态依次为 `signal`、`validating`、`awaiting_confirmation`；人工确认或合并后才写入正式主题本体。DeepSeek 可在后续深研中解释证据与补缺口，但不能绕过此状态机。

不可变报告与动态 ETF 现状分离：每个已确认主题使用 `theme-report:{theme_id}` 维护一条规范主报告版本链，`report_versions` 保存冻结正文、结构化结论、产业链、三情景、评分、ETF 格局与 claim-evidence 引用；`etf_market_snapshots` 保存独立手动刷新行情。只有通过发布质量门槛并经用户核实的研究运行才能原子追加版本；报告详情可按 `version` 读取冻结版本，`timeline`/`compare` 返回结论、评分、ETF 和证据缺口的结构化变化。刷新不会改写报告资产或内容哈希。

ETF 动态数据由确定性双源工作流生成。天天基金网提供境内基金档案、费率、规模、净值收益与场内指标，yfinance 提供全球交易所行情和成交活跃度。二者覆盖不同市场，合并层只对可确定匹配的产品和可比字段交叉验证，并为单源字段保留 provenance。逐 ticker 失败隔离、缓存、退避和冷却由代码与 `config/defaults.yaml` 控制；两源均无可用新数据时不写快照。

ETF 预览是独立采集的只读产品目录。`SyncDiscoveryWorker` 以 `etf-preview:daily:YYYY-MM-DD` 或 `etf-preview:manual:*` 幂等键领取采集任务，自动发现天天基金目录后先做确定性互斥分类，再逐基金读取公开档案、复权净值和交易状态。美股主动候选先排除明确的中国、港股、亚洲、日本、印度、越南、欧洲等地域产品；名称/概况未明确指向美国者，再用最新前十大持仓的市场代码与权重验证美国主要暴露。结果整批写入不可变 `etf_preview_snapshots`；单只基金失败被隔离，失败运行不会覆盖最后一次成功快照。主题报告在生成边界读取最新成功快照，按主题名称、确认别名和跟踪指数确定性匹配后将相关产品冻结进报告版本；不因美股/海外大类自动判定相关。场内产品的溢价使用同一日期的收盘价和单位净值，不能用不同日期数据或盘中估值替代。

现有连接器覆盖 SEC、OpenAlex、公开招聘、发行人 ETF 持仓、Yahoo Finance ETF 公开资讯及受控公开发现；来源按授权与可用性降级。ETF 信号不参与候选主题的最低成立条件，只在主题形成后描述可投资性与拥挤度，缺失时保持 `not_assessed`。

主题评分由配置与确定性代码共同驱动。只有在至少具备三类独立来源、其中一类为官方来源，且上市公司覆盖满足阈值时，主题才能获得高置信度。社交媒体与 Seeking Alpha 均为可选来源，默认关闭，不能单独支持产品发行结论。

## 2026-08-14 契约冻结基线

本节冻结阶段 0 / 任务 0.1 开始时的兼容面，不引入新业务行为。可运行 `python tools/export_contract_snapshot.py` 从临时 SQLite、FastAPI 路由表和 `frontend/src/services/*.ts` 重新导出机器可读 JSON，并用 `tests/test_api_contracts.py` 检查关键项。

### 服务身份与报告标识

- 服务 ID：`etf-theme-radar`。
- 公共契约版本：`2026-08-05.v9`；`/health` 与 `/api/capabilities` 必须报告相同版本。本任务未新增或改变公共 API，因此不提升版本。
- 新规范主题主报告使用 `theme-report:{theme_id}`。旧资产 `report:{run_id}` 仍是受支持标识；API 路由边界只解码一次，并通过 `run_registry` 定位独立运行数据库。`GET /api/reports/{report_id}/detail` 等报告路由不得将 `report:` 前缀改写成新标识。

### SQLite 表

当前应用表共 31 张；SQLite 内部的 `sqlite_*` 表不计入契约：

| 领域 | 表 |
|---|---|
| 原始证据与治理 | `raw_documents`、`normalized_events`、`citations`、`connector_health` |
| 主题与评分 | `themes`、`theme_aliases`、`theme_snapshots`、`theme_scores` |
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
