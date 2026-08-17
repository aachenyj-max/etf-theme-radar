# 每日简报资产与首页 API 设计

## 目标

每日同步在完成治理后，将合格证据冻结为可追溯的每日简报资产；首页仅读取最新资产，并提供主题、产业链位置和来源的下钻，以及质量和来源健康异常的聚合统计。

## 方案

新增独立的 `daily_briefing_assets` 表，而不复用主题报告的 `report_assets`。每行是一份按日期生成的简报快照，保存资产 ID、截至日、生成时间、所含 evidence ID、结构化 payload 和内容哈希。`as_of_date` 唯一，重新生成同一日的简报时以完整、原子替换更新当天资产；历史日期不受影响。

`SyncDiscoveryWorker` 在来源同步、确定性治理和候选发现完成后，以本地日期创建或刷新当天资产。构建器只读取 `EvidenceStore.publishable_events()`；不合格事件绝不进入简报 payload、事实卡或下钻结果。保留 `build_daily_brief()` CLI 函数，但改由同一个结构化 payload 渲染 Markdown，避免其与 API 计算口径分叉。

`GET /api/dashboard` 仍是只读 API，读取最新资产。可选参数 `theme`、`industry_chain` 和 `source` 对资产内事实卡作合取筛选；响应返回简报元数据、筛选后事件、三个可用于继续下钻的 facet 和异常统计。异常统计只返回内容质量的非 `publishable` 状态计数及来源健康的 `degraded`/`disabled` 聚合，不把未通过质量门的事件当作简报信息暴露。

## 数据与错误处理

如果没有已生成资产，首页返回一致的空简报结构和零计数，不在 GET 路径创建数据。简报生成的存储写入使用一次短事务；结构化 payload 中的事件是最小安全事实集（证据 ID、标题、摘要、时间、主题、来源与已审计的产业链位置）。产业链位置只从 `extracted_facts` 中状态为 `audited` 的记录读取；缺失时为 `unknown`，不由模板推断。

## 契约、测试与文档

公开首页响应与新增资产表构成服务契约变更：`CONTRACT_VERSION` 升至 `2026-08-17.v16`，启动器和契约快照测试同步更新。测试先覆盖：质量门排除、同日资产持久化、下钻交集、异常聚合、空资产行为以及 v16 导出路由/表。同步 README、AGENTS、架构、数据字典、运行手册与进度记录。

指定回归命令为：

```powershell
python -m pytest tests/test_daily_briefing.py tests/test_api_contracts.py -q
```

本任务按用户要求不在本次执行；交付只列出该命令和相关检查清单。
