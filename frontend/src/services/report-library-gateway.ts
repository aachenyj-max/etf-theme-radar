import type {
  ReportAssistantResult,
  ReportLibraryFilters,
  ReportLibraryGateway,
  ReportLibrarySnapshot,
  ReportStatus,
  ResearchReportAsset
} from "@/lib/report-library";

const initialReports: ResearchReportAsset[] = [
  {
    id: "report_ai_infrastructure",
    runId: "rr_ai_20260722",
    title: "AI 基础设施 ETF 主题研究",
    kind: "theme_report",
    themeId: "ai-infrastructure",
    themeLabel: "AI 基础设施",
    folder: "ai",
    status: "deep_research",
    tags: ["AI", "半导体", "ETF"],
    summary: "梳理算力、网络互连、电力与数据中心基础设施的跨来源证据，并明确商业化与产品空白的待验证事项。",
    updatedAt: "2026-07-22T15:40:00Z",
    createdAt: "2026-07-18T09:00:00Z",
    version: 6,
    sourceCount: 7,
    evidenceCount: 42,
    auditPassed: true
  },
  {
    id: "report_aether_event",
    runId: "rr_aether_20260719",
    title: "模块化 AI 数据中心公开事件研究",
    kind: "event_report",
    themeId: "ai-infrastructure",
    themeLabel: "AI 基础设施",
    folder: "ai",
    status: "watch",
    tags: ["AI", "数据中心", "事件"],
    summary: "区分公司公告、二级报道与尚未核验的订单、收入和部署假设，形成后续核验清单。",
    updatedAt: "2026-07-19T12:20:00Z",
    createdAt: "2026-07-19T10:00:00Z",
    version: 3,
    sourceCount: 4,
    evidenceCount: 11,
    auditPassed: true
  },
  {
    id: "report_nuclear_landscape",
    title: "先进核能与 SMR ETF 格局扫描",
    kind: "landscape_scan",
    themeId: "nuclear-energy",
    themeLabel: "核能与先进反应堆",
    folder: "energy",
    status: "completed",
    tags: ["核能", "SMR", "ETF"],
    summary: "整理现有核能 ETF 暴露、上市公司覆盖和监管时间线，标记燃料链与项目周期风险。",
    updatedAt: "2026-07-17T08:50:00Z",
    createdAt: "2026-07-10T11:00:00Z",
    version: 4,
    sourceCount: 6,
    evidenceCount: 37,
    auditPassed: true
  },
  {
    id: "report_grid_modernization",
    title: "电网现代化产业动量周报",
    kind: "evidence_brief",
    themeId: "grid-modernization",
    themeLabel: "电网现代化",
    folder: "energy",
    status: "watch",
    tags: ["电网", "电力设备", "数据中心"],
    summary: "跟踪输配电资本计划、变压器交付周期与数据中心接入瓶颈的周度变化。",
    updatedAt: "2026-07-15T17:10:00Z",
    createdAt: "2026-06-28T09:30:00Z",
    version: 5,
    sourceCount: 5,
    evidenceCount: 31,
    auditPassed: true
  },
  {
    id: "report_robotics_commercialization",
    title: "智能机器人商业化证据复核",
    kind: "theme_report",
    themeId: "robotics",
    themeLabel: "智能机器人",
    folder: "robotics",
    status: "deep_research",
    tags: ["机器人", "制造", "自动化"],
    summary: "比较试点、量产、订单和收入证据，避免将通用招聘与演示事件误判为商业采用。",
    updatedAt: "2026-07-14T14:45:00Z",
    createdAt: "2026-07-05T13:00:00Z",
    version: 7,
    sourceCount: 6,
    evidenceCount: 35,
    auditPassed: true
  },
  {
    id: "report_robotics_counter",
    title: "机器人主题反方证据检索",
    kind: "evidence_brief",
    themeId: "robotics",
    themeLabel: "智能机器人",
    folder: "robotics",
    status: "draft",
    tags: ["机器人", "反方证据"],
    summary: "整理部署延迟、客户预算、单位经济性与量产爬坡不及预期的公开证据。",
    updatedAt: "2026-07-12T10:30:00Z",
    createdAt: "2026-07-12T09:00:00Z",
    version: 2,
    sourceCount: 3,
    evidenceCount: 14,
    auditPassed: false
  },
  {
    id: "report_healthcare_ai",
    title: "医疗 AI 基础设施初步扫描",
    kind: "landscape_scan",
    themeId: "healthcare-ai",
    themeLabel: "医疗 AI",
    folder: "healthcare",
    status: "watch",
    tags: ["医疗", "AI", "合规"],
    summary: "扫描医疗模型部署、数据治理与监管约束，目前仍缺少足够的商业化和上市公司映射证据。",
    updatedAt: "2026-07-08T16:15:00Z",
    createdAt: "2026-07-01T10:20:00Z",
    version: 2,
    sourceCount: 4,
    evidenceCount: 19,
    auditPassed: true
  },
  {
    id: "report_ai_packaging_archive",
    title: "先进封装研究简报｜历史版本",
    kind: "theme_report",
    themeId: "advanced-semiconductor-packaging",
    themeLabel: "先进半导体封装",
    folder: "ai",
    status: "archived",
    tags: ["半导体", "先进封装", "历史版本"],
    summary: "已归档的先进封装主题简报，保留当时的来源、评分和审计附件。",
    updatedAt: "2026-06-20T11:30:00Z",
    createdAt: "2026-05-18T08:00:00Z",
    version: 4,
    sourceCount: 5,
    evidenceCount: 28,
    auditPassed: true
  }
];

let reports = initialReports.map((report) => ({ ...report, tags: [...report.tags] }));

const folderMeta = {
  ai: { label: "人工智能", englishLabel: "AI" },
  energy: { label: "能源与电力", englishLabel: "Energy" },
  robotics: { label: "智能机器人", englishLabel: "Robotics" },
  healthcare: { label: "医疗健康", englishLabel: "Healthcare" }
} as const;

const themeLabelMap: Record<string, string> = {
  "ai-infrastructure": "AI 基础设施",
  "edge-ai-infrastructure": "边缘 AI 基础设施",
  robotics: "智能机器人",
  semiconductors: "半导体",
  "nuclear-energy": "核能与先进反应堆",
  "grid-modernization": "电网现代化",
  "healthcare-ai": "医疗 AI"
};

function matchesDate(updatedAt: string, range: ReportLibraryFilters["dateRange"], sourceReports: ResearchReportAsset[]) {
  if (range === "all") return true;
  const days = range === "30d" ? 30 : range === "90d" ? 90 : 365;
  const latest = Math.max(...sourceReports.map((report) => new Date(report.updatedAt).getTime()));
  return new Date(updatedAt).getTime() >= latest - days * 86_400_000;
}

function buildSnapshot(filters: ReportLibraryFilters, sourceReports: ResearchReportAsset[] = reports): ReportLibrarySnapshot {
  const query = filters.query.trim().toLocaleLowerCase();
  const filtered = sourceReports
    .filter((report) => filters.folder === "all" || report.folder === filters.folder)
    .filter((report) => filters.status === "all" ? report.status !== "archived" : report.status === filters.status)
    .filter((report) => matchesDate(report.updatedAt, filters.dateRange, sourceReports))
    .filter((report) => !query || `${report.title} ${report.themeLabel} ${report.tags.join(" ")} ${report.summary}`.toLocaleLowerCase().includes(query))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));

  const folders = (Object.keys(folderMeta) as Array<keyof typeof folderMeta>).map((id) => {
    const folderReports = sourceReports.filter((report) => report.folder === id && report.status !== "archived");
    return {
      id,
      ...folderMeta[id],
      reportCount: folderReports.length,
      latestUpdate: folderReports.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0]?.updatedAt
    };
  });

  return {
    state: filtered.length ? "ready" : "empty",
    reports: filtered,
    folders,
    totalBeforeFilters: sourceReports.length,
    activeCount: sourceReports.filter((report) => report.status !== "archived").length,
    archivedCount: sourceReports.filter((report) => report.status === "archived").length,
    generatedAt: new Date().toISOString()
  };
}

function requireReport(reportId: string) {
  const report = reports.find((item) => item.id === reportId);
  if (!report) throw new Error("报告不存在或已经删除。");
  return report;
}

function assistantResult(command: string): ReportAssistantResult {
  const normalized = command.toLocaleLowerCase();
  if (normalized.includes("机器人") || normalized.includes("robotics")) {
    const matched = reports.filter((report) => report.folder === "robotics" && report.status !== "archived");
    return { title: "机器人研究", summary: `找到 ${matched.length} 份机器人研究，已按最近更新排序。`, matchedReportIds: matched.map((report) => report.id), suggestedFilters: { folder: "robotics", query: "" } };
  }
  if ((normalized.includes("比较") || normalized.includes("compare")) && normalized.includes("ai")) {
    const matched = reports.filter((report) => report.folder === "ai" && report.tags.includes("ETF") && report.status !== "archived");
    return { title: "AI ETF 报告对比", summary: `找到 ${matched.length} 份可用于对比的 AI ETF 研究。`, matchedReportIds: matched.map((report) => report.id), suggestedFilters: { folder: "ai", query: "ETF" } };
  }
  if (normalized.includes("变化") || normalized.includes("changes") || normalized.includes("更新")) {
    const matched = reports.filter((report) => report.status !== "archived").sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).slice(0, 3);
    return { title: "最近研究变化", summary: `最近更新集中在 ${[...new Set(matched.map((report) => report.themeLabel))].join("、")}，共 ${matched.length} 份重点文件。`, matchedReportIds: matched.map((report) => report.id), suggestedFilters: { dateRange: "30d", query: "" } };
  }
  const matched = reports.filter((report) => `${report.title} ${report.tags.join(" ")}`.toLocaleLowerCase().includes(normalized));
  return { title: "资料库搜索结果", summary: matched.length ? `找到 ${matched.length} 份相关研究。` : "没有找到直接匹配项，可以尝试主题、公司或报告类型。", matchedReportIds: matched.map((report) => report.id), suggestedFilters: matched.length ? { query: command } : undefined };
}

export const mockReportLibraryGateway: ReportLibraryGateway = {
  async listReports(filters) {
    return buildSnapshot(filters);
  },
  async getReport(reportId) {
    return { ...requireReport(reportId) };
  },
  async renameReport(reportId, title) {
    const report = requireReport(reportId);
    Object.assign(report, { title: title.trim(), updatedAt: new Date().toISOString(), version: report.version + 1 });
    return { ...report };
  },
  async archiveReport(reportId) {
    const report = requireReport(reportId);
    Object.assign(report, { status: "archived" as ReportStatus, updatedAt: new Date().toISOString() });
    return { ...report };
  },
  async deleteReport(reportId) {
    requireReport(reportId);
    reports = reports.filter((report) => report.id !== reportId);
  },
  async askLibrary(command) {
    return assistantResult(command);
  }
};

type ApiReportAsset = {
  report_id: string;
  run_id?: string;
  title: string;
  kind: string;
  theme_id: string;
  folder_id: string;
  status: string;
  tags: string | string[];
  summary: string;
  updated_at: string;
  created_at: string;
  version: number;
  source_count: number;
  evidence_count: number;
  audit_passed: number | boolean;
};

function parseTags(value: string | string[]) {
  if (Array.isArray(value)) return value;
  try { const parsed = JSON.parse(value); return Array.isArray(parsed) ? parsed.map(String) : []; } catch { return []; }
}

function mapApiReport(item: ApiReportAsset): ResearchReportAsset {
  const folder = (["ai", "energy", "robotics", "healthcare"].includes(item.folder_id) ? item.folder_id : "ai") as ResearchReportAsset["folder"];
  const status = (["deep_research", "watch", "completed", "draft", "archived"].includes(item.status) ? item.status : "completed") as ReportStatus;
  const kind = (["theme_report", "quick_scan", "etf_opportunity_analysis", "event_report", "landscape_scan", "evidence_brief"].includes(item.kind) ? item.kind : "theme_report") as ResearchReportAsset["kind"];
  return {
    id: item.report_id,
    runId: item.run_id,
    title: item.title,
    kind,
    themeId: item.theme_id,
    themeLabel: themeLabelMap[item.theme_id] ?? item.theme_id,
    folder,
    status,
    tags: parseTags(item.tags),
    summary: item.summary,
    updatedAt: item.updated_at,
    createdAt: item.created_at,
    version: item.version,
    sourceCount: item.source_count,
    evidenceCount: item.evidence_count,
    auditPassed: Boolean(item.audit_passed)
  };
}

export function createHttpReportLibraryGateway(baseUrl: string): ReportLibraryGateway {
  async function requestReport(reportId: string, init?: RequestInit) {
    const response = await fetch(`${baseUrl}/api/reports/${encodeURIComponent(reportId)}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
    if (!response.ok) throw new Error(response.status === 404 ? "报告不存在或已经删除。" : `报告接口返回 ${response.status}`);
    return mapApiReport(await response.json() as ApiReportAsset);
  }

  return {
    async listReports(filters) {
      const params = new URLSearchParams({ query: filters.query, folder: filters.folder, status: filters.status, date_range: filters.dateRange });
      const response = await fetch(`${baseUrl}/api/reports?${params.toString()}`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`报告接口返回 ${response.status}`);
      const payload = await response.json() as {
        reports: ApiReportAsset[];
        total_before_filters: number;
        active_count: number;
        archived_count: number;
        folders: Array<{ id: ResearchReportAsset["folder"]; report_count: number; latest_update?: string }>;
      };
      const mappedReports = payload.reports.map(mapApiReport);
      return {
        state: mappedReports.length ? "ready" : "empty",
        reports: mappedReports,
        folders: payload.folders.map((folder) => ({
          id: folder.id,
          ...folderMeta[folder.id],
          reportCount: folder.report_count,
          latestUpdate: folder.latest_update
        })),
        totalBeforeFilters: payload.total_before_filters,
        activeCount: payload.active_count,
        archivedCount: payload.archived_count,
        generatedAt: new Date().toISOString()
      };
    },
    getReport(reportId) {
      return requestReport(reportId);
    },
    renameReport(reportId, title) {
      return requestReport(reportId, { method: "PATCH", body: JSON.stringify({ title }) });
    },
    archiveReport(reportId) {
      return requestReport(reportId, { method: "PATCH", body: JSON.stringify({ status: "archived" }) });
    },
    async deleteReport(reportId) {
      const response = await fetch(`${baseUrl}/api/reports/${encodeURIComponent(reportId)}`, { method: "DELETE" });
      if (!response.ok) throw new Error(response.status === 404 ? "报告不存在或已经删除。" : `报告接口返回 ${response.status}`);
    },
    async askLibrary(command) {
      const response = await fetch(`${baseUrl}/api/reports/assistant`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command }) });
      if (!response.ok) throw new Error(`资料库助手返回 ${response.status}`);
      return await response.json() as ReportAssistantResult;
    }
  };
}

const reportApiBaseUrl = process.env.NEXT_PUBLIC_REPORTS_API_BASE_URL?.replace(/\/$/, "") ?? "";
export const reportLibraryGateway = createHttpReportLibraryGateway(reportApiBaseUrl);
