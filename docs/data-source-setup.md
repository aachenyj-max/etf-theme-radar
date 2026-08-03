# 数据源配置指南

所有密钥放入项目根目录 `.env`，不要提交或粘贴到对话中。启动前可复制 `.env.example` 并填写所需项目。

## SEC 新 ETF 注册

填写 `SEC_USER_AGENT="ETF Theme Radar 团队名 联系邮箱"`。系统扫描 SEC 每日表单索引中的 N-1A、485APOS、485BPOS、497、N-CSR 和 NPORT-P。无需 API Key，但必须遵守 SEC 的 User-Agent 与限速规则。

- 官方说明：[SEC EDGAR 数据 API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- 操作：提供可公开显示的团队联系邮箱；设置 `SEC_ENABLED=true`。

## 论文、专利与招聘

- OpenAlex：填写 `OPENALEX_MAILTO`；可选填写 `OPENALEX_API_KEY`。系统按主题词检索近期论文。入口：[OpenAlex](https://openalex.org/)。
- 专利：当前使用 `google_patents` 连接器，经 AnySearch 发现并严格保留 `patents.google.com` 公开链接；设置 `GOOGLE_PATENTS_ENABLED=true`，可用 `GOOGLE_PATENTS_QUERIES_JSON` 配置发现查询。这类结果只作为低置信度线索，必须交叉确认。需要账号和 API Key 的 PatentsView/USPTO 正式接口仍不接入，保持 `PATENTSVIEW_ENABLED=false`。
- 招聘：填写 `JOB_BOARDS_JSON`。每项包含公司名、`provider`（`greenhouse`、`lever`、`ashby` 或 `career_page`）及公开 board token；`career_page` 还需提供官方 URL，例如：

```json
[{"company":"示例公司","provider":"greenhouse","board":"example"},{"company":"另一公司","provider":"career_page","board":"another","url":"https://example.com/careers/"}]
```

Greenhouse、Lever 与 Ashby 只读取公开职位；`career_page` 保存官方招聘页面快照，置信度低于结构化招聘板。各公司逐项失败隔离，并由 `JOB_BOARDS_MAX_PER_RUN` 控制每轮数量。可从目标公司 careers 页面取得 board token，再参阅 [Greenhouse Job Board API](https://developer.greenhouse.io/job-board.html)、[Lever Postings API](https://github.com/lever/postings-api) 和 [Ashby Job Postings API](https://developers.ashbyhq.com/docs/public-job-posting-api)。

## ETF 持仓与公开讨论

默认从 `config/etf-competitor-universe.json` 读取 18 只 ETF 的发行人官方页面；`ETF_HOLDINGS_MAX_FEEDS_PER_RUN` 控制轮换数量。也可用 `ETF_HOLDINGS_FEEDS_JSON` 覆盖，每项包含 ticker、官方 URL 和 `csv`/`html` 格式，例如：

```json
[{"ticker":"示例ETF","url":"https://发行人官网/holdings.csv","format":"csv"}]
```

只接受发行人官方持仓文件、官方基金页面或 SEC N-PORT 作为权威持仓来源。AnySearch 使用 `ANYSEARCH_ENABLED=true` 开启，通过 `ANYSEARCH_QUERIES_JSON` 轮换 Google Patents、Seeking Alpha 等公开查询，并通过 `X_WATCHLIST_JSON` 轮换关注账号。Seeking Alpha 只保存公开标题、摘要和链接；不得抓取订阅内容或绕过访问控制。

ETF 公开资讯使用 `yahoo_etf_news` 连接器，经 yfinance 读取 `config/etf-competitor-universe.json` 中 ETF ticker 的公开新闻元数据。设置 `YAHOO_ETF_NEWS_ENABLED=true`；`YAHOO_ETF_NEWS_MAX_TICKERS_PER_RUN` 和 `YAHOO_ETF_NEWS_MAX_ITEMS_PER_TICKER` 控制轮换与单 ticker 上限。该来源仅限个人研究、逐 ticker 失败隔离，只保存标题、发布时间、发布者、摘要和原始 URL；重要事实须由 SEC、发行人官方页面或其他独立来源确认。

## S&P Global 指数与 ETF 资讯

系统已预配置 `config/sp-global-public-feeds.json` 中的 S&P Dow Jones Indices 官方公开 RSS，覆盖指数公告、指数发布、方法论、研究、每日指数洞察和表现报告。2026-07-30 的后台透明 HTTP 客户端验证被 S&P 返回 403，因此 `SP_GLOBAL_ENABLED` 默认保持 `false`，前端显示为等待授权；不得通过伪装浏览器绕过。获得 S&P 明确允许的机器访问方式后，RSS 项会保留原始 S&P URL、发布日期、分类和 feed 名称，且单个 feed 失败不会中止其他来源。S&P DJI 明确保留随时停止 feed 分发的权利，因此该来源不能作为唯一证据。

公开 RSS 不包含 S&P Global Market Intelligence 的付费 ETF Intelligence 数据。ETF Intelligence 所述 fund flows、完整 holdings、exposures、concentration risk 和历史日频分析只有在取得正式授权、API 文档及凭据后才能接入；不得抓取产品登录页面或猜测私有接口。可用 `SP_GLOBAL_RSS_FEEDS_JSON` 覆盖公开 feed 列表，`SP_GLOBAL_CACHE_TTL_SECONDS` 控制缓存刷新间隔。
