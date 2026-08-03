# ETF Theme Radar 开发进度

> 最后更新：2026-07-29  
> 当前阶段：可靠 Worker、分阶段 Agent 审计、历史主题雷达、报告版本和三种研究输出已接通；进入真实数据覆盖与生产化加固阶段。

## 1. 项目目标与已确定原则

项目面向本地单用户的美国 ETF 主题研究场景，目标是把公开信息转化为可追溯、可复核的主题研究资产，而不是交易、证券推荐或正式 ETF 发行建议。

已确定的架构原则：

- 使用确定性 Workflow 管理采集、状态、评分、重试、审计和持久化。
- Agent 处理主题定义、语义判断、检索规划、工具选择和证据叙述；工具适配层负责受控落库，模型不能直接修改数据库或决定最终状态。
- 权威连接器优先；AnySearch 和 Playwright MCP 只作为公开信息发现/降级层。
- 主题定义和最终报告必须经过用户复核。
- 退回报告后由用户决定是否重跑；通过报告后由用户决定是否归档。
- 模型密钥只保存在后端 `.env`，不得进入浏览器、报告或数据库。
- 数据不足时显示 `unknown`、`insufficient_data` 或真实空状态，不回退 mock 填充。

## 2. 本次已完成

### 2.1 持久化状态与数据库

- 扩展 `research_runs`，保存完整研究请求、进度、复核门禁、attempt 和错误。
- 新增 `run_steps`、`approvals`、`tool_calls` 表。
- 增加研究步骤、审批历史、任务列表和 attempt 操作接口。
- 服务启动时恢复 `planning/queued/collecting/governing/analyzing/auditing` 状态的中断任务。
- Schema 升级前使用 SQLite backup API 创建 `*.pre-schema-v2.bak`。
- 保持原有 EvidenceStore 和测试接口兼容。

主要文件：

- `etf_theme_radar/store.py`
- `etf_theme_radar/workflow.py`

### 2.2 主题报告工作流

当前真实流程：

```text
planning
→ awaiting_theme_review
→ queued
→ collecting
→ governing
→ analyzing
→ awaiting_report_review
→ completed
```

同时支持 `returned`、`failed`、`cancelled`。

已实现：

- 任意主题输入，不再只接受四个预置主题。
- 模型可生成主题名称、描述、别名、包含/排除词和研究问题。
- 未配置模型时使用确定性主题定义模板。
- 用户可以通过或退回主题定义。
- 研究执行前重新治理已有证据。
- 主题报告支持自定义主题名称和别名匹配。
- 最终报告进入独立人工复核门禁。
- 退回不会自动重跑；显式调用 rerun 才创建新 attempt。
- 通过后注册报告资产，但不自动归档。
- 运行中取消后，Workflow 不再覆盖 `cancelled` 状态。

主要 API：

- `POST /api/research-runs`
- `GET /api/research-runs/{run_id}`
- `POST /api/research-runs/{run_id}/theme-review`
- `POST /api/research-runs/{run_id}/report-review`
- `POST /api/research-runs/{run_id}/rerun`
- `POST /api/research-runs/{run_id}/cancel`

### 2.3 数据同步与真实聚合 API

- 增加启动后台增量同步和旧数据重新治理。
- 增加手动同步 API：`POST /api/sync`。
- 修复 pipeline store 未关闭的问题。
- 增加首页聚合：`GET /api/dashboard`。
- 增加真实主题列表：`GET /api/themes`。
- 增加动态证据筛选项：`GET /api/evidence/facets`。
- 增加模型、连接器、MCP 和输出类型能力状态：`GET /api/capabilities`。
- 连接器健康、证据、报告和报告详情原有 API 继续保留。

### 2.4 前端真实 API 接入

- Next.js 使用同源 rewrite 将 `/api/*` 转发到 FastAPI，避免浏览器 CORS。
- 首页改为读取真实 dashboard、主题和研究任务。
- 来源墙改为读取真实连接器健康状态。
- 主题雷达改为读取真实主题 API。
- 研究工作台改为真实异步任务轮询。
- 增加主题定义复核、报告复核、退回备注、重跑和取消操作。
- 证据浏览器和报告库默认使用 HTTP Gateway，不再默认回退 mock。
- 证据公司和主题筛选优先读取动态 facets。
- 快速扫描和 ETF 机会分析显示“后续开放”且不可选择。
- 产品工作室继续保持锁定。

主要文件：

- `frontend/src/components/dashboard-workspace.tsx`
- `frontend/src/components/research-workspace.tsx`
- `frontend/src/components/theme-radar-workspace.tsx`
- `frontend/src/services/*-gateway.ts`
- `frontend/next.config.mjs`

### 2.5 Playwright MCP

- 新增 `etf_theme_radar/browser_mcp.py`。
- 使用官方 Python MCP SDK，通过 stdio 调用 Playwright MCP。
- MCP 依赖为懒加载，普通研究流程不会加载工具 schema 或启动浏览器。
- 仅允许 HTTP/HTTPS；阻止初始 URL 指向 localhost、内网、链路本地和保留地址。
- 支持域名 allowlist：`PUBLIC_BROWSER_ALLOWED_DOMAINS`。
- 默认 headless、isolated、文件输出。
- 当前只会在启用 MCP 且已有相关 AnySearch 候选 URL 时抓取最多三个公开页面。
- 页面结果作为二级发现证据写入原始文档和标准化事件，后续仍需治理。

### 2.6 配置、Skill 和启动方式

- `scoring.py` 改为从 `config/defaults.yaml` 读取权重和证据门槛。
- `.env.example` 增加启动同步、LLM 和 Playwright MCP 配置。
- 新建项目 Skill：`skills/etf-theme-research/`。
- Skill 只保存主题定义、反方证据、引用与报告方法，不包含业务代码。
- `policy.allow_implicit_invocation=false`，避免无关任务自动加载该 Skill。
- `启动ETF主题雷达.bat` 现在调用 `tools/start_local.ps1`，同时启动 FastAPI 和 Next.js。
- 两个进程均在本地隐藏窗口运行；主窗口退出时停止服务。
- 日志写入 `data/logs/`。

## 3. 当前验证状态

最后一次验证结果：

- `python -m pytest -q -p no:cacheprovider`：37 passed。
- `python -m compileall -q etf_theme_radar`：通过。
- `npm.cmd run lint`：通过。
- `npm.cmd run build`：通过，9 个 Next.js 路由成功构建。
- `npm.cmd run test:e2e`：2 passed（本机 Edge；主题复核/退回/重跑/通过与报告归档）。
- FastAPI 实际进程联调：`/health`、`/api/capabilities`、`/api/dashboard`、`/api/themes` 均可访问。
- Skill frontmatter、引用文件和 UI metadata 人工结构检查通过。

已知非功能警告：

- pytest 无法建立 `.pytest_cache`，报 WinError 183；不影响测试结果。
- Skill 官方 `quick_validate.py` 因当前 Python 环境缺少 PyYAML 无法运行，因此本次采用人工结构校验。
- 当前目录没有可用 Git 仓库，无法通过 `git diff/status` 生成变更摘要或提交。

## 4. 本地运行

首次或依赖变化后：

```powershell
python -m pip install -e .
cd frontend
npm install
```

随后双击根目录：

```text
启动ETF主题雷达.bat
```

地址：

```text
前端：http://127.0.0.1:3000
API：http://127.0.0.1:8000/docs
```

Playwright MCP 默认关闭。需要启用时在真实 `.env` 中配置：

```env
PLAYWRIGHT_MCP_ENABLED=true
PLAYWRIGHT_MCP_COMMAND=npx.cmd
```

建议通过 `PLAYWRIGHT_MCP_ARGS` 固定经过审计的 `@playwright/mcp` 版本，不要长期依赖未固定版本。

## 5. 重要已知限制

### P0：状态和安全

1. 当前恢复机制会从阶段起点重放任务，但还不是租约式 Worker；服务崩溃可能重复外部请求。
2. `run_steps` 有幂等主键，但外部工具调用尚未全部使用稳定 idempotency key。
3. 取消无法中断已经进入的同步 LLM/报告生成调用，只能阻止其最终覆盖状态。
4. Agent 调用的连接器、AnySearch 与 MCP 已写入 `tool_calls`；启动同步、主题定义和最终分析的调用仍待统一。
5. Playwright 只校验初始 URL；浏览器重定向后的最终地址尚未重新执行私网/域名策略验证。
6. 网页正文尚未实现专门的 prompt-injection 清洗和隔离，只依靠研究提示和二级来源治理。
7. API 仅适合绑定 `127.0.0.1`；没有认证、授权和 CSRF 设计，不得暴露公网。
8. 自定义 `database_path` 的创建路径与后续 review/rerun 默认数据库路由还未完全统一；前端默认数据库不受影响。

### P1：研究质量

1. Agent 目前主要参与主题定义和受控报告摘要，尚未实现计划中的三轮检索规划/反思循环。
2. 只限制单次模型输出 token，尚未统计并硬限制整个 run 的总 token、总工具数和总时间。
3. 反方检索仍以“缺失证据”模板为主，没有独立的 counter-search Agent 步骤。
4. 可投资公司映射、pure play/enabler/beneficiary 分类仍不完整。
5. ETF 竞争格局、持仓重叠和产品空白仍为 `unknown/insufficient_data`。
6. 通用事件深挖仍未改造；Aether 事件研究包含专用硬编码事实包。
7. 主题状态和雷达分数目前是聚合启发式，不是完整的 `ThemeMetrics + opportunity_score` 快照链。
8. 趋势当前固定为 `stable` 并提示历史不足，尚未建立 30/90/365 日历史比较。
9. 新开放主题的分类仍主要依靠别名文本匹配，没有持久化动态主题本体和人工编辑后的定义。

### P2：前端和运维

1. 顶部全局搜索、系统设置和用户头像仍没有真实功能。
2. 启动同步没有前端全局进度与取消界面。
3. 报告退回备注目前使用 `window.prompt`，应改成正式 Dialog 和历史记录 UI。
4. 首页、主题和报告的空状态可以继续优化，但不得恢复 mock。
5. 尚未加入 Playwright 自动化 E2E 测试；现有验证为后端测试、类型检查和构建。
6. `.env` 真实文件不会被自动改写；新增配置需用户从 `.env.example` 手工合并。

### 5.1 2026-07-28 Agent V1 增量

- 采用 PydanticAI，不引入 LangGraph/CrewAI/AutoGen；保留现有 SQLite Workflow 管理阶段、审批和确定性结果。
- 新增 DeepSeek V4 模型分工：`deepseek-v4-flash` 负责工具循环，`deepseek-v4-pro` 负责主题定义和证据分析；通过统一 Provider 配置保留切换能力。
- 新增七个类型化工具：查询证据、来源健康、权威连接器采集、AnySearch、Playwright MCP、证据缺口和结束研究。
- 工具循环默认限制为 6 个模型请求、12 次工具调用和 720 秒；连续两次采集无新增证据后停止继续采集。
- 新增 `agent_runs` 表并扩展 `tool_calls`，保存 prompt 哈希、模型、token、停止原因、参数/结果摘要、延迟、重试和证据增量。
- `GET /api/research-runs/{run_id}` 已返回 Agent 与工具审计；研究页展示模型、停止原因和最近工具调用。
- system prompt 已迁移到 `etf_theme_radar/prompts/`，不再散落在工作流源码中。
- 明文模型 key 不再从研究 API 请求体传入，只读取后端 `.env`；`.env.example` 使用空占位符。
- 新增 FunctionModel 离线 Agent 工具选择测试以及 key 不泄露测试。
- 本次验证：`python -m pytest -q` 为 24 passed；前端 `npm.cmd run lint` 通过。

## 6. 下一阶段开发任务

### 第一优先级：把状态机做成可靠任务执行器

- 为 run/step 增加 `lease_owner`、`lease_expires_at`、heartbeat 和稳定 idempotency key。
- 将后台 Thread 替换为单进程持久 Worker loop；API 只负责创建任务和状态操作。
- 将主题定义和最终分析两类 LLM 调用也统一写入 `tool_calls`；Agent 工具、AnySearch 和 MCP 已接入。
- 增加阶段级重试，而不是重放整个 execute workflow。
- 修复 custom database path 路由，所有 run 操作从 run metadata 解析数据库。
- 为取消、失败、退回、重跑和服务恢复增加并发/竞争条件测试。

### 第二优先级：强化有界 Agent 研究循环（V1 已接通）

- 增加独立步骤：`query_planning → evidence_gap_analysis → counter_search → synthesis`。
- 增加可配置总 token 和成本上限；当前已限制 6 个模型请求、12 次工具调用和 12 分钟。
- 使用 Pydantic schema 校验每轮输出；一次修复失败后回退确定性模板。
- Agent 已只能从工具注册表选择来源；继续增加工具级域名策略和更细粒度权限测试。
- 实现网页内容不可信隔离：删除页面指令、只保留事实文本和元数据。
- MCP 导航后检查最终 URL 与网络请求，阻止重定向到私网或未允许域名。
- 工具失败按 429、超时、5xx、403、解析失败分别处理并记录降级原因。

### 第三优先级：主题本体、实体和历史雷达

- 正式实现 `theme_aliases`、`theme_snapshots`、`entities`、`entity_aliases`、`entity_links`。
- 保存用户确认或修改后的主题定义，而不是只放在 result JSON。
- 增加公司/ticker/ETF 实体消歧和人工确认队列。
- 每次同步生成主题指标快照，使用 `config/defaults.yaml` 的完整评分规则。
- 只有至少两个可比快照时才计算 emerging/stable/cooling。
- 首页和雷达展示分项计算、覆盖率和真实趋势原因。

### 第四优先级：研究质量和报告

- 实现通用反方证据搜索与冲突证据映射。
- 实现上市公司可投资性、美国可交易覆盖和集中度评估。
- 接入官方 ETF competitor universe 和持仓重叠计算。
- 移除 Aether 专用事件逻辑，改成通用事件事实包工作流。
- 将 report claims 与 evidence 建立结构化多对多引用。
- 增加不可变 `report_versions` 和前端版本比较。
- 把退回备注和复核历史改成正式前端组件。

### 第五优先级：另外两种输出和产品体验

- 先实现快速扫描：复用主题工作流，但降低检索深度，只输出证据摘要和缺口。
- 再实现 ETF 机会分析：增加竞争产品、官方持仓、指数规则、流动性和集中度。
- 只有对应后端 capability 和测试通过后才解除前端禁用。
- ETF 产品工作室继续锁定，直到可投资性和 ETF 格局完成并经人工审核。
- 接通全局搜索、系统能力页和同步任务状态 UI。

### 测试与验收

- 增加真实 FastAPI TestClient 契约测试。
- 增加完整前端 Playwright E2E：主题确认、报告复核、退回、重跑、归档。
- 增加服务在每个阶段退出后的恢复测试。
- 增加 MCP 假服务器测试、重定向攻击和页面 prompt injection 测试。
- 真实连接器 smoke test 保持为显式运行，不进入离线 CI 必过集合。

## 7. 下次开发建议起点

建议下次不要先扩展新数据源，按以下顺序开始：

1. 阅读本文件、`etf_theme_radar/workflow.py`、`store.py` 和新增工作流测试。
2. 实现 lease-based Worker 和统一 tool-call audit。
3. 补齐状态恢复、取消和重跑的竞争条件测试。
4. 实现有界 counter-search Agent，并先用 fixture/fake LLM 验证。
5. 再接通 Playwright MCP 的最终 URL 校验和 prompt-injection 防护。
6. 完成后运行：

```powershell
python -m pytest -q
python -m compileall -q etf_theme_radar
cd frontend
npm.cmd run lint
npm.cmd run build
```

任何真实数据结论继续遵守：来源可追溯、缺口明确、不得将演示/缓存/二级发现描述成实时持仓、AUM、SEC 最终状态或投资建议。

## 8. 2026-07-29 完成增量（本节取代第 5～7 节中的旧待办状态）

### 可靠执行与审计

- 研究任务改为 SQLite lease-based 单进程持久 Worker，不再为每个研究任务创建 daemon Thread。
- 主题研究与通用事件研究共用同一 Worker/lease/registry 路径；事件 API 也不再单独启动研究 Thread。
- `research_runs` 和 `run_steps` 已加入 lease owner、过期时间、heartbeat、稳定 idempotency key 与阶段 retry 记录。
- collecting、governing、analyzing、auditing 按持久化阶段逐项推进，恢复时不再从整个 workflow 起点重放。
- 复核、取消和重跑使用 compare-and-set；自定义 `database_path` 通过持久 `run_registry` 解析。
- 主题定义、最终证据综合、Agent 工具、AnySearch 和 MCP 均进入统一 `tool_calls` 审计；外部采集工具支持幂等回放。

### Agent、安全与研究资产

- Agent 审计步骤明确记录 `query_planning → evidence_gap_analysis → counter_search → synthesis`，结束前强制 `finish_research`；未配置模型时也记录确定性 fallback 和跳过原因。
- 整个 run 支持总 token、估算成本、模型请求、工具调用和总时长预算；Pydantic 输出仅允许一次修复，失败后进入确定性降级。
- 工具失败区分 429、timeout、403、5xx、parse error 和 unexpected error。
- Playwright MCP 导航后复核最终 URL 与网络请求 URL；页面正文移除 prompt-injection 指令行，并以 `untrusted-sanitized` 标记落库。
- 新增 `theme_aliases`、`theme_snapshots`、`entities`、`entity_aliases`、`entity_links`；用户通过的主题定义会持久化。
- 每次治理后生成确定性主题快照；只有两个日期可比后才计算 emerging/stable/cooling，并返回分项、惩罚、覆盖率与趋势原因。

### 报告、输出与前端

- 通用反方候选映射、上市公司/ticker 初步角色分类、集中度和官方 ETF competitor universe/持仓覆盖已接入；未由交易所、指数或完整持仓核验的数据保持 `unknown`/`not_assessed`。
- Aether 专用事实包和硬编码 SEC URL 已移除，事件深挖改为按主题/公司匹配独立一级来源的通用事实包。
- 新增不可变 `report_versions`、`report_claims`、`report_claim_evidence`，以及版本列表、比较 API 和前端比较视图。
- 快速扫描与 ETF 机会分析已开放并由 capability 驱动；ETF 产品工作室继续按合规要求锁定。
- 新增全局搜索、系统能力/同步页、可取消同步任务、正式退回 Dialog 与复核历史。
- 新增 FastAPI TestClient 契约、lease 竞争、custom DB、阶段恢复、快照趋势、prompt injection、输出模式、报告版本和 Playwright E2E 测试。

### 当前仍需真实数据或生产环境才能关闭的边界

1. Worker 仍是本地单进程，不是跨主机分布式队列；上游不接受幂等键时，外部成功而本地提交前崩溃仍可能在 lease 过期后重试。
2. 已进入的同步 LLM、连接器或浏览器调用无法被 Python 强制安全中断，只能在返回后阻止状态覆盖。
3. API 没有公网认证、授权和 CSRF 设计，只允许绑定 `127.0.0.1`。
4. Playwright 已审计最终地址和 MCP 返回的网络请求，但 service worker、WebSocket 等浏览器侧通道仍需更底层网络沙箱才能完全覆盖。
5. 美国交易所证券主表、完整 ETF 持仓、指数规则和流动性源尚无足够官方数据；对应结果保持 `unknown`/`not_assessed`，产品工作室不解锁。
6. 正式连接器 smoke test 仍需显式联网运行，不进入离线必过测试。
7. `npm audit --omit=dev` 当前报告 Next.js 间接依赖的 PostCSS（无上游可用修复）和 sharp/libvips（需要 sharp 0.35+，超出现有 Next 依赖范围）共 3 个 high；未使用 `--force` 或不兼容 override。应用只绑定本机且不处理用户提交 CSS/图片，但仍需跟踪 Next 官方依赖升级。
