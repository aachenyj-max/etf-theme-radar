export const toolLabels: Record<string, string> = {
  llm_theme_definition: "DeepSeek 主题定义",
  llm_evidence_synthesis: "DeepSeek 证据综合",
  llm_event_fact_analysis: "DeepSeek 事件事实分析",
  inspect_source_health: "检查信息源状态",
  collect_from_source: "采集选定信息源",
  search_public_web: "搜索公开网页",
  browse_public_page: "浏览公开页面",
  query_existing_evidence: "检索已有证据",
  summarize_gaps: "汇总证据缺口",
  finish_research: "完成研究采集"
};

export const statusLabels: Record<string, string> = {
  running: "进行中", succeeded: "已完成", completed: "已完成", failed: "失败",
  skipped: "已跳过", blocked: "受阻", cancelled: "已取消",
  healthy: "正常", degraded: "降级", disabled: "已关闭",
  high: "高", medium: "中", low: "低", unknown: "未知"
};

export const sourceTypeLabels: Record<string, string> = {
  sec: "SEC 文件", regulatory: "监管文件", academic: "学术论文", paper: "研究论文",
  patent: "专利", job: "公司招聘", jobs: "公司招聘", company_update: "公司动态",
  social: "社交媒体讨论", forum: "论坛讨论", social_discussion: "市场讨论", official: "官方来源"
};

export function labelFor(mapping: Record<string, string>, value?: string, fallback = "未知") {
  if (!value) return fallback;
  return mapping[value] ?? mapping[value.toLowerCase()] ?? value;
}
