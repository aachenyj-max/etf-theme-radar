# ETF Theme Radar（ETF 主题雷达）

面向美国注册 ETF 产品团队的、以证据为中心的内部研究 MVP。系统用于发现主题、整理公开证据、计算可解释评分并支持产品研究；不会交易、连接券商账户、生成买卖指令或生成正式 SEC 申报文件。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m etf_theme_radar.cli demo --db data/radar.db --output data/demo-output.json
python -m uvicorn etf_theme_radar.api:app --host 127.0.0.1 --port 8001 --reload
```

启动后访问 `http://127.0.0.1:8001/docs` 查看基金经理 Dashboard API；前端固定为 `http://127.0.0.1:3000`。演示流程完全使用确定性 fixture，不会请求真实 SEC 或社交平台数据。

## 已实现能力

- 基于 SQLite 的原始证据库：保留来源 URL、内容哈希、获取时间、访问说明、解析版本和置信度。
- 统一 Connector 协议，以及 SEC EDGAR、OpenAlex、Google Patents 公开发现、公开招聘板/公司 Careers 页面、发行人 ETF 持仓页面、Yahoo Finance ETF 公开资讯和 AnySearch 公开发现适配器。
- SEC 适配器内置联系人型 User-Agent 校验、限速、缓存、重试与失败降级机制。
- 事件标准化、证据多样性门槛、确定性主题机会评分和产品白空间评分。
- FastAPI 健康检查、主题与证据只读接口，以及 JSON 输出能力。
- PydanticAI 驱动的有界研究 Agent：DeepSeek V4 Flash 自主选择只读工具，V4 Pro 负责主题定义和证据综合。
- Agent 运行、模型用量和工具调用的 SQLite 审计记录；前端展示行动时间线但不展示隐藏思维链。
- SQLite lease-based 单进程持久 Worker：支持 heartbeat、阶段级恢复、稳定幂等键及复核/取消/重跑的原子状态转换；启动同步与任务治理在单进程内串行执行，重分类每 10 条释放写锁，heartbeat 遇到瞬时锁会继续重试而不会终止线程。新证据在 `ingest` 时逐条确定性分类，普通研究任务只刷新实体和主题快照；全库重分类仅在启动或显式来源同步时执行。
- 研究任务使用“1 个活动槽 + 1 个等待槽”的 SQLite 原子队列；第三项返回 `409 TASK_QUEUE_FULL`。待复核与退回任务继续占用活动槽，退回任务可显式结束并原子提升等待项。
- 持久主题本体、别名、实体待复核队列和主题指标快照；只有两个可比快照后才输出 emerging/stable/cooling。
- 不可变报告版本、结构化 claim↔evidence 多对多引用、版本比较 API 与前端比较视图。
- 研究运行证据账本同时展示原始入库增量和治理后主题有效增量，能够解释缓存、去重与主题过滤造成的数量差异。
- 报告正文中的 ETF 格局保持版本冻结；Yahoo/yfinance 价格与成交活跃度位于独立 `etf_market_snapshots`。手动刷新由持久 Worker 生成新快照，不改变报告版本、正文或结论；限流失败优先使用最后一次成功缓存。
- 支持与反方证据优先展示经审计的中文标题、事实摘要和研究含义；品牌、公司、ticker 与协议保留官方写法，界面仅通过来源按钮访问原文。
- 重点证据事实摘要使用一至两句自然中文概括原文明示的发表时间、作者或机构、领域/地点和主要事件或观点；缺失项不推断。摘要按唯一 evidence ID 生成并逐条审计，单条失败不会使整批证据退回固定模板。
- ETF 静态竞品清单现在是优先缓存而非封闭全集：已授权 ETF 行情且已核验候选不足时，DeepSeek 会通过受预算约束的公开搜索工具发现全球上市 ETF；只有具备发行人/交易所官方 HTTPS 页面、交易所、市场、币种和 Yahoo symbol 的候选才能进入本次报告快照。
- 报告在执行摘要前展示证据约束的“研究结论”（支持/混合/证据不足）。DeepSeek 只能引用已入库证据和已有数字；越过证据门槛或审计失败时自动降级为确定性结论。
- 三种真实输出：快速扫描、主题研究报告和 ETF 机会分析；数据不足时返回 `unknown`、`insufficient_data` 或 `not_assessed`。
- 全局研究资产搜索、系统能力页、可取消同步任务，以及带历史记录的正式复核退回 Dialog。
- 招聘与 ETF 来源轮换采集、逐项失败隔离和 403/超时降级；离线 mock fixture、单元测试和 Connector 契约测试。
- S&P Dow Jones Indices 来源入口与官方品牌图标：已预配置指数公告、指数发布、方法论、研究、每日指数洞察和表现报告 feed；后台访问当前返回 403，默认关闭并等待正式 API/机器访问授权。付费 ETF Intelligence 数据仅在取得正式授权后接入。

## 项目结构

```text
etf_theme_radar/    核心包：连接器、证据库、流程、评分和 API
tests/              pytest 测试与离线 fixture
config/             可调整的评分权重与指数约束
docs/               架构、数据字典、运行手册及 Skill 审计
skills/             项目本地安装的允许 Skills
```

## 当前边界与下一步

2026-07-29 的独立验证库实测采集 703 条事件：OpenAlex 30 条、公开招聘 630 条、AnySearch 40 条、ETF 官方页面 4 条；两个 ETF 页面返回 403 后被单独降级，SEC 在测试窗口内无匹配文件但接口正常。另行验证的公开发现查询返回 10 个 Google Patents 链接和 10 个 Seeking Alpha 公开链接。该结果仅证明当次链路可运行，不代表持续覆盖率或生产 SLA。当前按项目决策暂不接入需要账号和 API Key 的 PatentsView/USPTO 正式专利接口，`PATENTSVIEW_ENABLED` 保持关闭；`google_patents` 默认启用，经 AnySearch 发现公开专利链接，作为低置信度补充，不需要注册专利 API。

使用真实 SEC 数据前，请在环境变量中设置带联系方式的 `SEC_USER_AGENT`。默认关注 15 家公司、15 个 X 账号和 `config/etf-competitor-universe.json` 中的 18 只 ETF；批量来源按运行轮换，单次不保证覆盖全部对象。`yahoo_etf_news` 使用 yfinance 获取这些 ETF 的公开新闻元数据，每轮默认轮换 4 只，仅限个人研究并作为二级线索。社交数据、Google Patents、Yahoo Finance 和 Seeking Alpha 发现结果不得单独支持结论；不得绕过登录、验证码、付费墙、robots 或其他访问控制。

ETF 机会分析使用 240 秒自适应快速档，最多 8 次工具和 4 次模型请求：优先读取持久证据与缓存，再查发行人官方持仓和 Yahoo Finance ETF 公开资讯，证据仍不足时才补 Google Patents 或一次反方检索。Yahoo 元数据缓存 30 分钟，官方持仓缓存 6 小时；已确认主题自动继续，新主题仍等待人工确认。所有任务保留反方检查、DeepSeek 综合与 `finish_research` 审计。

ETF 行情仅限个人研究和二级发现。成交量、成交额及其变化是交易活跃度代理，不能解释为买入人数或资金净流入；AUM、净申购、指数规则和美国可交易状态未由可靠来源核验时保持 `unknown`/`not_assessed`。
全球 ETF 行情保留各自交易币种和交易所；不同币种的成交额不做横向排名，只对百分比收益等无量纲指标进行同类比较。动态发现结果按报告版本冻结，不会自动写回全局竞品配置。

## 文档与合规提示

请阅读以下文档：

- [架构说明](docs/architecture.md)
- [数据字典](docs/data-dictionary.md)
- [运行手册与限制](docs/runbook.md)
- [Skill 审计](docs/skill-audit.md)
- [数据源配置指南](docs/data-source-setup.md)
- [贡献规范](AGENTS.md)

所有输出均为内部研究草案，必须由基金法务、合规、指数、AP/做市和上市团队复核；它们不构成投资、法律、税务或合规意见。

## 本地真实闭环

Windows 用户可双击 `启动ETF主题雷达.bat`。唯一前端为 `http://127.0.0.1:3000`，唯一 API 为 `http://127.0.0.1:8001`。启动器不再自动漂移端口；若固定端口被非本项目进程或旧契约占用，会明确报错。重复启动只会在服务身份、契约版本与 Worker 心跳全部匹配时复用现有实例，并通过 `data/runtime/launcher.lock` 防止并发创建多组服务。运行日志写入 `data/logs/`，关闭启动窗口只停止本次启动器新建的服务。
重复双击 BAT 复用健康服务时也会打开前端页面；PowerShell 返回后 BAT 会保留成功或失败结果并等待按键，不再一闪而过。
启动器也会兼容部分桌面宿主同时注入 `Path` 与 `PATH` 的环境，避免 Windows PowerShell 5.1 因重复环境键而无法创建子进程。

当前默认流程为：创建研究任务 → 新主题确认定义（已确认主题的 ETF 分析自动继续）→ Worker 按阶段采集/治理/分析/审计 → 人工通过或退回报告 → 报告库。退回不会自动重跑，通过不会自动归档。ETF 机会分析会在官方持仓、上市公司、指数规则或流动性不足时明确保留缺口。

侧栏数据覆盖与研究工作台来源可用性均读取 `/api/capabilities`；关闭或降级的来源会明确标记且不能选入新任务，不使用硬编码覆盖数字。
研究工作台以左侧任务账本展示需要处理、正在运行、等待中和历史任务；`?run=<run_id>` 保留当前选择。切换任务不影响后台执行，活动项继续使用 SSE，连接失败时回退为状态轮询。
任务详情的幂等 GET 在 Next 开发服务器重编译或代理瞬时中断时会短暂重试一次；持续断线会在工作区显示可读错误，不再触发 Next.js Runtime Error 覆盖层。写操作不会自动重放。
新建任务区保留卡片式研究目标、情报来源和输出类型选择；来源卡片的可用状态仍来自 `/api/capabilities`。任务列表 GET 接口属于 `2026-07-31.v4` 契约，若界面提示旧版 API 或返回 405，应先关闭旧服务再重新双击启动器。
研究工作台通过 `GET /api/research-runs/{run_id}/stream` 接收 SSE 审计行动流，实时显示阶段、工具状态、证据增量与异常，不展示模型隐藏思维链。连接中断时前端自动回退到 2 秒轮询并定期尝试重连；人工复核和终态会关闭当次流。

前端默认使用同源 API，不再回退 mock。数据库没有治理后证据时，首页、主题雷达和证据浏览器会显示真实空状态；启动同步和后续研究会逐步填充证据。模型密钥仅配置在后端 `.env` 的 `DEEPSEEK_API_KEY`，不得使用浏览器端环境变量保存密钥。复制 `.env.example` 后填写已轮换的新 key；不要使用曾在聊天、日志或源码中暴露过的 key。Playwright MCP 为公开网页降级能力。
报告详情路由对 `report:run_id` 只执行一次 URL 解码；报告库、历史书签和详情 API 必须继续兼容现有带冒号的报告 ID。用户可见的信息源、运行状态与工具名称以中文显示，SEC、OpenAlex、arXiv、Google Patents、Seeking Alpha、X、ETF 等品牌或缩写保留英文。

## 新增运行与测试入口

- `GET /api/search`：搜索主题、证据和报告。
- `POST/GET /api/sync-runs`：创建并观察可取消的同步任务。
- `GET /api/entities/review`：读取实体消歧待复核队列。
- `GET /api/reports/{report_id}/versions` 与 `/compare`：读取不可变版本和行级差异。
- `GET /api/research-runs`：分页读取任务账本、进度、等待位置与人工处理状态。
- `POST /api/reports/{report_id}/market-snapshot`：由持久 Worker生成独立 ETF 现状快照，不修改报告版本。
- `npm.cmd run test:e2e`：通过 Playwright + 本机 Edge 验证主题复核、报告退回、重跑、通过和归档。
- `python -m etf_theme_radar.cli backfill-evidence-summaries --db data/radar.db`：预览旧固定证据摘要的升级范围；增加 `--apply` 后以不可变 `V+1` 版本写入，旧版本与引用保持不变。

当前可靠性边界：Worker 是本地单进程实现，不是分布式队列；同步连接器、LLM 或浏览器已经进入同步调用后只能在返回时响应取消。上游不支持幂等键时，进程在外部调用成功但本地提交前崩溃仍可能在 lease 过期后重试。API 仍只允许绑定本机，不具备公网认证、授权或 CSRF 防护。ETF 流动性、指数规则和美国交易所主表尚未接入时不会推断结论。

供应链提示：2026-07-29 的 `npm audit --omit=dev` 对 Next.js 间接依赖报告 3 个 high（PostCSS 上游暂无可用修复；sharp/libvips 的修复版本超出现有 Next 依赖范围）。项目未使用 `--force` 或未经验证的 override；本地应用不接受用户 CSS/图片输入，但仍应在 Next 发布兼容依赖后升级并复跑 build/E2E。
