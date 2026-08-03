export type SourceState = "正常" | "延迟" | "待配置";

export const sourceIntelligence = [
  { name: "SEC", label: "监管文件", domain: "sec.gov", logo: "https://www.sec.gov/files/sec-logo.png", state: "正常" as SourceState, freshness: "8 分钟前" },
  { name: "arXiv", label: "学术论文", domain: "arxiv.org", logo: "https://cdn.simpleicons.org/arxiv/B31B1B", state: "正常" as SourceState, freshness: "18 分钟前" },
  { name: "Google Patents", label: "专利", domain: "patents.google.com", logo: "https://cdn.simpleicons.org/google/4285F4", state: "正常" as SourceState, freshness: "34 分钟前" },
  { name: "X", label: "市场讨论", domain: "x.com", logo: "https://cdn.simpleicons.org/x/10273D", state: "延迟" as SourceState, freshness: "2 小时前" },
  { name: "iShares", label: "ETF 持仓", domain: "ishares.com", logo: "https://www.google.com/s2/favicons?domain=ishares.com&sz=128", state: "正常" as SourceState, freshness: "1 小时前" },
  { name: "Nasdaq", label: "公司公告", domain: "nasdaq.com", logo: "https://www.google.com/s2/favicons?domain=nasdaq.com&sz=128", state: "正常" as SourceState, freshness: "27 分钟前" },
  { name: "Greenhouse", label: "招聘", domain: "greenhouse.io", logo: "https://cdn.simpleicons.org/greenhouse/357E63", state: "正常" as SourceState, freshness: "42 分钟前" },
  { name: "Seeking Alpha", label: "投资论坛", domain: "seekingalpha.com", logo: "https://www.google.com/s2/favicons?domain=seekingalpha.com&sz=128", state: "待配置" as SourceState, freshness: "等待授权" }
];

export const metrics = [
  { label: "观察主题", value: "12", detail: "4 个进入重点跟踪", trend: "+2 本周" },
  { label: "有效证据", value: "1,284", detail: "一级来源占比 61%", trend: "+8.4%" },
  { label: "研究任务", value: "6", detail: "2 个等待审核", trend: "3 进行中" },
  { label: "来源覆盖", value: "7/8", detail: "1 个来源待配置", trend: "稳定" }
];

export const themes = [
  { slug: "ai-infrastructure", title: "AI 基础设施", status: "重点研究", score: 82, evidence: 146, change: "+18%", sources: 7, summary: "算力扩容、数据中心电力与网络互连形成连续证据链。" },
  { slug: "edge-ai-infrastructure", title: "边缘 AI 基础设施", status: "持续观察", score: 68, evidence: 71, change: "+7%", sources: 5, summary: "端侧推理部署增加，但商业化证据仍集中于少数厂商。" },
  { slug: "robotics", title: "机器人", status: "持续观察", score: 64, evidence: 93, change: "+4%", sources: 6, summary: "产业招聘与专利信号改善，收入兑现仍需交叉核验。" }
];

export const researchTasks = [
  { title: "AI 基础设施主题简报", theme: "AI 基础设施", stage: "证据分析", progress: 72, owner: "研究组", updated: "12 分钟前" },
  { title: "机器人商业化反方检索", theme: "机器人", stage: "交叉核验", progress: 46, owner: "M. Chen", updated: "1 小时前" },
  { title: "半导体 SEC 新产品扫描", theme: "半导体", stage: "等待审核", progress: 100, owner: "产品研究", updated: "昨天" }
];

export const evidenceItems = [
  { id: "EV-2026-0718", source: "SEC", sourceType: "监管原始文件", title: "某注册人提交新增系列文件，策略聚焦数据中心基础设施", confidence: 0.96, date: "2026-07-21", theme: "AI 基础设施" },
  { id: "EV-2026-0694", source: "arXiv", sourceType: "学术论文", title: "面向大规模推理集群的光互连架构研究", confidence: 0.91, date: "2026-07-20", theme: "AI 基础设施" }
];

export const reports = [
  { title: "AI 基础设施｜基金经理两页简报", status: "WATCH", date: "2026-07-21", sources: 7, evidence: 42, kind: "主题简报" },
  { title: "模块化数据中心公开事件研究", status: "待复核", date: "2026-07-19", sources: 4, evidence: 11, kind: "事件深度报告" }
];
