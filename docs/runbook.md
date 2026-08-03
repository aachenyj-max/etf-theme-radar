# 运行手册与限制

启用 SEC 数据获取前，必须将 `SEC_USER_AGENT` 设置为包含联系信息的值。不得降低限速、规避访问限制或使用未授权凭据。数据源异常时，请检查 `connector_health` 和 pipeline 错误记录；其他来源应继续运行，同时相应降低结论置信度。

当前唯一已验证的端到端流程是 fixture 演示。示例中的标识、分数和事件均为模拟数据，不能被当作实时信号、真实持仓、AUM、SEC 状态或回测结果。

## 研究运行实时流

研究工作台默认连接 `/api/research-runs/{run_id}/stream` 获取 SSE 审计快照。正常情况下会实时显示阶段和工具调用；浏览器或代理中断流式连接时自动回退到 2 秒轮询，并每 10 秒尝试恢复 SSE。等待人工复核或任务进入终态时连接会正常关闭。该信息流只包含持久化审计记录，不包含模型隐藏思维链。

证据进度包含两个口径：`raw_added` 是去重后写入证据库的新记录，`relevant_added` 是确定性治理后归属于当前主题的有效新增。两者不一致是正常现象，前端会展示基线、当前值和两个增量。

任务队列最多包含一个活动项和一个等待项。第三次创建返回 `409` 与 `TASK_QUEUE_FULL`；先完成/取消活动项，或取消等待项。`returned` 不会自动释放活动槽，可选择重跑或调用 `POST /api/research-runs/{run_id}/finish` 结束。使用 `GET /api/research-runs` 检查等待位置与 `needs_attention`。

若 `GET /api/research-runs` 返回 405 且响应头只允许 POST，说明 8001 仍运行旧契约进程。关闭旧启动窗口或对应的本项目服务后重新启动；v4 启动器不会复用缺少任务列表 GET 的 v3 服务。

## DeepSeek Agent 配置

复制 `.env.example` 为本地 `.env`，设置新的 `DEEPSEEK_API_KEY`。默认由 `deepseek-v4-flash` 执行阶段内工具选择，由 `deepseek-v4-pro` 执行主题定义与最终证据分析。旧的 `deepseek-chat`、`deepseek-reasoner` 名称不再使用。

Agent 只能调用注册的公开来源工具，标准档默认最多 6 个模型轮次、12 次工具调用和 480 秒。ETF 机会分析使用 240 秒快速档，最多 4 次模型请求和 8 次工具调用，优先缓存、官方 ETF 持仓与 Yahoo Finance ETF 公开资讯；官方持仓缓存 6 小时，Yahoo 元数据缓存 30 分钟。默认值位于 `config/defaults.yaml`。未配置 key 时流程使用确定性离线路径；401、模型不存在等配置错误会进入 `blocked_configuration`。

通过固定 API `http://127.0.0.1:8001/api/capabilities` 检查服务身份、契约版本、Worker 心跳、`7/8` 来源覆盖、模型与工具注册状态；固定前端为 `http://127.0.0.1:3000`。通过 `GET /api/research-runs/{run_id}` 查看 `agent_runs` 与 `tool_calls`。响应不会包含 API key 或模型隐藏推理内容。

所有产品材料仅为内部研究草案。使用前必须经过基金法务、合规、指数、AP/做市商和交易所上市团队复核。系统不提供投资、法律、税务或合规意见，也不执行任何交易。

## ETF 市场快照

包含 ETF 章节且授权 `etf_news` 的报告可通过 `POST /api/reports/{report_id}/market-snapshot` 创建持久刷新任务。任务只写入独立 `etf_market_snapshots`，不改变报告版本、正文哈希或结论。请求按 ticker 节流，对 429 有限退避并记录失败冷却；失败时优先返回最后成功缓存并标记 `stale`/`stale_if_error`，没有历史成功值时才显示不可用。指标包括 1月价格收益、最新价与成交活跃度等；成交活跃度不代表买入人数或资金流。

## 故障排查

- `SEC_USER_AGENT is required`：在本地 `.env` 中设置联系人型 User-Agent，且不要提交该文件。
- Connector 状态为 `disabled`：检查环境变量中的开关；关闭可选来源不应影响 fixture 或其他来源。
- 外部请求失败：保留错误记录，使用缓存或 fixture 验证流程，不得伪造抓取结果。
- `blocked_configuration`：检查 key、账户权限、`LLM_BASE_URL` 和 V4 模型名，修复后重新运行任务。
## 历史证据摘要升级

先使用 dry-run 查看仍包含旧固定模板的报告：

```powershell
python -m etf_theme_radar.cli backfill-evidence-summaries --db data/radar.db
```

确认后显式增加 `--apply`。升级会追加不可变报告版本并原子提升资产指针，不修改旧版本；重复执行保持幂等。命令只使用报告中已经冻结的证据，不重新访问来源网页。失败报告会保留原版本并在 JSON 结果的 `failed` 中列出。
