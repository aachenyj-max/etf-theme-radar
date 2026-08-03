# Skill 审计

审计日期：2026-07-21。初始两份指定仓库下载到本仓库的 `.agents/skill-sources/`；随后应用户明确请求，额外安装了 `anysearch-ai/anysearch-skill`。所有可用 Skill 都位于仓库本地 `skills/`，未安装到全局 Codex 目录。许可证：`himself65/finance-skills` 为 MIT，`anthropics/financial-services` 和 `anysearch-ai/anysearch-skill` 为 Apache-2.0；使用时须保留相应许可证与 NOTICE。

| 来源与本地 Skill | 可复用用途 | 输入 / 输出 | 依赖与限制 | 项目调用位置 |
|---|---|---|---|---|
| `finance-skills` → `etf-premium` | ETF 净值溢价/折价与同类产品诊断 | ETF 代码 → 溢价、净值与价差背景 | 依赖 yfinance/Yahoo；非官方 ETF 记录，可能限流或失败 | 后续 ETF 全景适配器；当前不参与评分 |
| `finance-skills` → `stock-liquidity` | ADTV、价差和市场冲击代理指标 | 代码/历史数据 → 流动性诊断 | 依赖 yfinance；属于代理指标，不能替代真实容量数据 | 后续指数纳入资格筛选 |
| `finance-skills` → `yfinance-data` | 公开市场数据获取模式 | 代码/查询 → 价格与基本面 | yfinance 公开端点；必须有缓存和失败处理 | 可选市场数据适配器，MVP 默认关闭 |
| `financial-services` → `idea-generation` | 主题扫描和候选公司分类框架 | 主题/规则 → 研究候选清单 | 必须独立验证，不能直接构成推荐 | 主题至证券的人工复核流程 |
| `financial-services` → `competitive-analysis` | 可比产品和竞争格局的证据框架 | 产品集合 → 带引用的竞争格局 | 原始来源优先；原设计偏向演示文稿工作流 | 产品白空间复核 |
| `financial-services` → `sector-overview` | 行业映射与证据提纲 | 行业/主题 → 行业结构 | 定性框架；所有数值均须有引用 | 基金经理简报流程 |
| `anysearch-ai/anysearch-skill` → `anysearch` | 实时网页、垂直领域、批量搜索与页面内容提取 | 查询或 URL → 搜索结果 / Markdown 正文 | 搜索查询和 URL 会发送至 AnySearch；匿名模式配额较低，API Key 可选；不得发送密钥、个人信息或未公开投资信息 | 公开 Twitter/X、论坛、学术和网页发现的可选补充层 |

## 未纳入的 Skill

社交阅读器、付费数据、TradingView、LinkedIn、Funda 和交易相邻 Skills 经过审计但未纳入。它们与公开/免费数据优先政策冲突、访问稳定性不足或不适合研究 MVP。AnySearch 是用户明确批准的例外，仅作为公开信息发现层，不能绕过登录、付费墙或来源限制，也不能替代正式数据连接器。缺失数据能力仍应以项目内可替换 adapter 实现。
