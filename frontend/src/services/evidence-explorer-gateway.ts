import type {
  EvidenceExplorerFilters,
  EvidenceExplorerGateway,
  EvidenceRecord,
  EvidenceSnapshot,
  EvidenceSourceType
} from "@/lib/evidence-explorer";

const sourceLogos: Record<EvidenceSourceType, string> = {
  sec: "https://www.sec.gov/files/sec-logo.png",
  paper: "https://cdn.simpleicons.org/arxiv/B31B1B",
  patent: "https://cdn.simpleicons.org/google/4285F4",
  job: "https://cdn.simpleicons.org/greenhouse/357E63",
  company_update: "https://www.google.com/s2/favicons?domain=nvidia.com&sz=128",
  social_discussion: "https://cdn.simpleicons.org/x/10273D"
};

export const mockEvidenceRecords: EvidenceRecord[] = [
  {
    id: "EV-2026-0718",
    sourceType: "sec",
    sourceLabel: "SEC 文件",
    publisher: "U.S. Securities and Exchange Commission",
    publisherDomain: "sec.gov",
    logoUrl: sourceLogos.sec,
    title: "数据中心基础设施相关资本开支与供应约束披露",
    publishedAt: "2026-07-21T14:30:00Z",
    summary: "公司监管文件继续将加速计算、网络互连和数据中心扩容列为资本配置重点，同时提示供电与交付周期约束。",
    qualityLabel: "监管原始文件",
    primaryOrSecondary: "primary",
    sourceQuality: 0.98,
    confidence: 0.96,
    originalUrl: "https://www.sec.gov/edgar/search/",
    extractedFacts: [
      "文件将数据中心扩容列入资本开支重点。",
      "网络互连与供电能力被列为部署约束。",
      "披露未单独给出 AI 基础设施业务收入。"
    ],
    relatedCompanies: ["NVIDIA", "大型云服务商"],
    relatedThemes: [{ id: "ai-infrastructure", label: "AI 基础设施" }, { id: "grid-modernization", label: "电网现代化" }]
  },
  {
    id: "EV-2026-0709",
    sourceType: "company_update",
    sourceLabel: "公司动态",
    publisher: "NVIDIA Newsroom",
    publisherDomain: "nvidia.com",
    logoUrl: sourceLogos.company_update,
    title: "新一代计算平台将网络、加速器与机架级系统协同设计",
    publishedAt: "2026-07-21T09:10:00Z",
    summary: "公司更新强调机架级系统、互连和软件栈协同，说明竞争边界正从单一芯片扩展到完整计算基础设施。",
    qualityLabel: "公司官方公告",
    primaryOrSecondary: "primary",
    sourceQuality: 0.91,
    confidence: 0.93,
    originalUrl: "https://nvidianews.nvidia.com/",
    extractedFacts: [
      "官方材料以机架级系统而非单一芯片描述产品。",
      "网络互连与软件栈被纳入统一架构。",
      "产品发布不能直接证明客户部署规模或收入兑现。"
    ],
    relatedCompanies: ["NVIDIA"],
    relatedThemes: [{ id: "ai-infrastructure", label: "AI 基础设施" }, { id: "semiconductors", label: "半导体" }]
  },
  {
    id: "EV-2026-0694",
    sourceType: "paper",
    sourceLabel: "研究论文",
    publisher: "arXiv",
    publisherDomain: "arxiv.org",
    logoUrl: sourceLogos.paper,
    title: "面向大规模推理集群的高带宽光互连架构研究",
    publishedAt: "2026-07-20T16:00:00Z",
    summary: "研究讨论推理集群扩展时的带宽、延迟与能耗瓶颈，为光互连在 AI 计算基础设施中的必要性提供技术侧证据。",
    qualityLabel: "学术研究",
    primaryOrSecondary: "primary",
    sourceQuality: 0.89,
    confidence: 0.91,
    originalUrl: "https://arxiv.org/search/?query=optical+interconnect+AI+clusters&searchtype=all",
    extractedFacts: [
      "研究对象是大规模推理集群的互连瓶颈。",
      "论文比较了带宽、延迟和能耗约束。",
      "学术可行性不等同于商业部署。"
    ],
    relatedCompanies: ["光模块与网络设备供应商"],
    relatedThemes: [{ id: "ai-infrastructure", label: "AI 基础设施" }, { id: "optical-networking", label: "光通信" }]
  },
  {
    id: "EV-2026-0672",
    sourceType: "patent",
    sourceLabel: "专利",
    publisher: "Google Patents",
    publisherDomain: "patents.google.com",
    logoUrl: sourceLogos.patent,
    title: "液冷数据中心的热管理与模块化部署专利族继续扩展",
    publishedAt: "2026-07-18T11:25:00Z",
    summary: "相关专利覆盖冷却回路、机架热管理和模块化部署，显示高密度计算带来的工程问题正在形成持续研发投入。",
    qualityLabel: "公开专利文件",
    primaryOrSecondary: "primary",
    sourceQuality: 0.9,
    confidence: 0.88,
    originalUrl: "https://patents.google.com/?q=(AI+data+center+cooling)",
    extractedFacts: [
      "专利主题覆盖液冷回路和机架热管理。",
      "多个申请围绕模块化部署展开。",
      "专利数量不能单独证明产品收入或竞争优势。"
    ],
    relatedCompanies: ["数据中心设备厂商", "冷却系统供应商"],
    relatedThemes: [{ id: "ai-infrastructure", label: "AI 基础设施" }, { id: "data-center-cooling", label: "数据中心制冷" }]
  },
  {
    id: "EV-2026-0648",
    sourceType: "job",
    sourceLabel: "公司招聘",
    publisher: "Microsoft Careers",
    publisherDomain: "jobs.careers.microsoft.com",
    logoUrl: "https://cdn.simpleicons.org/microsoft/5E5E5E",
    title: "数据中心电力、网络和部署岗位出现跨地区增量",
    publishedAt: "2026-07-16T08:40:00Z",
    summary: "去重后的技术岗位覆盖电力工程、网络架构和数据中心部署，反映基础设施建设能力仍在扩充，但岗位发布不代表收入。",
    qualityLabel: "公司官方招聘",
    primaryOrSecondary: "primary",
    sourceQuality: 0.88,
    confidence: 0.86,
    originalUrl: "https://jobs.careers.microsoft.com/global/en/search",
    extractedFacts: [
      "去重岗位涉及电力工程、网络和部署职能。",
      "信号覆盖多个地区而非单一办公地点。",
      "招聘计划可能调整，不能直接推导资本开支或收入。"
    ],
    relatedCompanies: ["Microsoft"],
    relatedThemes: [{ id: "ai-infrastructure", label: "AI 基础设施" }, { id: "grid-modernization", label: "电网现代化" }]
  },
  {
    id: "EV-2026-0617",
    sourceType: "social_discussion",
    sourceLabel: "市场讨论",
    publisher: "X / Industry Analysts",
    publisherDomain: "x.com",
    logoUrl: sourceLogos.social_discussion,
    title: "市场讨论开始从 GPU 供给转向电力与网络瓶颈",
    publishedAt: "2026-07-14T19:20:00Z",
    summary: "多位产业观察者讨论数据中心供电、变压器交付和互连能力，但该信号主要用于发现问题，不作为高置信度事实。",
    qualityLabel: "社交讨论",
    primaryOrSecondary: "secondary",
    sourceQuality: 0.42,
    confidence: 0.68,
    originalUrl: "https://x.com/search?q=AI%20data%20center%20power%20networking&src=typed_query",
    extractedFacts: [
      "讨论焦点包含供电、变压器和网络互连。",
      "多个账号表达相似观点。",
      "相关陈述尚未全部获得一级来源交叉核验。"
    ],
    relatedCompanies: ["公用事业公司", "网络设备供应商"],
    relatedThemes: [{ id: "ai-infrastructure", label: "AI 基础设施" }, { id: "grid-modernization", label: "电网现代化" }]
  },
  {
    id: "EV-2026-0581",
    sourceType: "sec",
    sourceLabel: "SEC 文件",
    publisher: "U.S. Securities and Exchange Commission",
    publisherDomain: "sec.gov",
    logoUrl: sourceLogos.sec,
    title: "网络设备公司披露 AI 集群带来的订单结构变化",
    publishedAt: "2026-07-09T13:15:00Z",
    summary: "监管披露显示高速网络产品需求占比提高，但客户集中度和订单确认节奏仍是判断持续性的关键限制。",
    qualityLabel: "监管原始文件",
    primaryOrSecondary: "primary",
    sourceQuality: 0.98,
    confidence: 0.94,
    originalUrl: "https://www.sec.gov/edgar/search/",
    extractedFacts: [
      "高速网络产品需求在披露期内提高。",
      "客户集中度仍然较高。",
      "订单不能在交付和验收前等同于已确认收入。"
    ],
    relatedCompanies: ["网络设备供应商"],
    relatedThemes: [{ id: "ai-infrastructure", label: "AI 基础设施" }]
  },
  {
    id: "EV-2026-0526",
    sourceType: "company_update",
    sourceLabel: "公司动态",
    publisher: "Vertiv Investor Relations",
    publisherDomain: "vertiv.com",
    logoUrl: "https://www.google.com/s2/favicons?domain=vertiv.com&sz=128",
    title: "高密度计算推动电源与热管理产品组合更新",
    publishedAt: "2026-07-03T10:00:00Z",
    summary: "公司材料将高密度计算负载与电源、液冷需求联系起来，为基础设施价值链扩展提供公司层面证据。",
    qualityLabel: "公司官方材料",
    primaryOrSecondary: "primary",
    sourceQuality: 0.9,
    confidence: 0.89,
    originalUrl: "https://investors.vertiv.com/",
    extractedFacts: [
      "公司材料将高密度计算与电源和热管理需求关联。",
      "产品组合包含液冷和配电能力。",
      "公司陈述需要与订单、交付和客户数据交叉核验。"
    ],
    relatedCompanies: ["Vertiv"],
    relatedThemes: [{ id: "ai-infrastructure", label: "AI 基础设施" }, { id: "data-center-cooling", label: "数据中心制冷" }]
  }
];

const themeLabels: Record<string, string> = {
  "ai-infrastructure": "AI 基础设施",
  "grid-modernization": "电网现代化",
  semiconductors: "半导体",
  robotics: "智能机器人"
};

function withinDateRange(publishedAt: string, dateRange: EvidenceExplorerFilters["dateRange"]) {
  if (dateRange === "all") return true;
  const days = dateRange === "30d" ? 30 : dateRange === "90d" ? 90 : 365;
  const latestDate = Math.max(...mockEvidenceRecords.map((item) => new Date(item.publishedAt).getTime()));
  return new Date(publishedAt).getTime() >= latestDate - days * 86_400_000;
}

function filterRecords(filters: EvidenceExplorerFilters) {
  return mockEvidenceRecords
    .filter((item) => filters.sourceType === "all" || item.sourceType === filters.sourceType)
    .filter((item) => withinDateRange(item.publishedAt, filters.dateRange))
    .filter((item) => filters.company === "all" || item.relatedCompanies.includes(filters.company))
    .filter((item) => item.relatedThemes.some((theme) => theme.id === filters.theme))
    .sort((a, b) => b.publishedAt.localeCompare(a.publishedAt));
}

function buildSnapshot(filters: EvidenceExplorerFilters, evidence: EvidenceRecord[]): EvidenceSnapshot {
  const averageConfidence = evidence.length ? evidence.reduce((sum, item) => sum + item.confidence, 0) / evidence.length : 0;
  return {
    state: evidence.length ? "ready" : "empty",
    filters,
    themeLabel: themeLabels[filters.theme] ?? filters.theme,
    confidenceLevel: averageConfidence >= 0.85 ? "high" : averageConfidence >= 0.65 ? "medium" : "low",
    confidenceScore: averageConfidence,
    primarySourceCount: evidence.filter((item) => item.primaryOrSecondary === "primary").length,
    sourceTypeCount: new Set(evidence.map((item) => item.sourceType)).size,
    totalBeforeFilters: mockEvidenceRecords.length,
    evidence,
    generatedAt: new Date().toISOString()
  };
}

export const mockEvidenceExplorerGateway: EvidenceExplorerGateway = {
  async listEvidence(filters) {
    const evidence = filterRecords(filters);
    return buildSnapshot(filters, evidence);
  },
  async getEvidence(evidenceId) {
    const record = mockEvidenceRecords.find((item) => item.id === evidenceId);
    if (!record) throw new Error("证据不存在或已从当前研究范围移除。");
    return record;
  }
};

type ApiEvidenceEvent = {
  event_id: string;
  source?: string;
  source_url: string;
  source_type?: string;
  title: string;
  summary?: string;
  published_at?: string;
  themes?: string | string[];
  companies?: string | string[];
  source_quality?: number;
  extraction_confidence?: number;
  origin_source_type?: string;
  publisher?: string;
  publisher_domain?: string;
  primary_or_secondary?: string;
  primary_theme?: string;
  secondary_themes?: string | string[];
  classification_reasons?: string | string[];
};

function parseStringList(value?: string | string[]) {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function mapApiSourceType(event: ApiEvidenceEvent): EvidenceSourceType {
  const value = `${event.origin_source_type ?? ""} ${event.source_type ?? ""}`.toLowerCase();
  if (value.includes("sec") || value.includes("regulatory") || value.includes("filing")) return "sec";
  if (value.includes("academic") || value.includes("paper") || value.includes("arxiv")) return "paper";
  if (value.includes("patent")) return "patent";
  if (value.includes("job") || value.includes("career")) return "job";
  if (value.includes("social") || value.includes("forum") || value.includes("twitter")) return "social_discussion";
  return "company_update";
}

function mapApiEvent(event: ApiEvidenceEvent): EvidenceRecord {
  const sourceType = mapApiSourceType(event);
  const relatedThemeIds = [
    event.primary_theme,
    ...parseStringList(event.secondary_themes),
    ...parseStringList(event.themes)
  ].filter((value): value is string => Boolean(value) && value !== "unknown");
  const relatedCompanies = parseStringList(event.companies);
  const reasons = parseStringList(event.classification_reasons);
  const primary = event.primary_or_secondary === "primary";

  return {
    id: event.event_id,
    sourceType,
    sourceLabel: sourceOptionsByType[sourceType],
    publisher: event.publisher || event.source || "未知发布者",
    publisherDomain: event.publisher_domain || "",
    logoUrl: sourceLogos[sourceType],
    title: event.title,
    publishedAt: event.published_at || new Date(0).toISOString(),
    summary: event.summary || "该证据尚未生成可展示摘要。",
    qualityLabel: primary ? "一级来源" : "二级来源",
    primaryOrSecondary: primary ? "primary" : "secondary",
    sourceQuality: event.source_quality ?? 0,
    confidence: event.extraction_confidence ?? 0,
    originalUrl: event.source_url,
    extractedFacts: reasons.length ? reasons : [event.summary || "暂无结构化事实。"],
    relatedCompanies: relatedCompanies.length ? relatedCompanies : [event.publisher || event.source || "待识别机构"],
    relatedThemes: [...new Set(relatedThemeIds)].map((id) => ({ id, label: themeLabels[id] ?? id }))
  };
}

const sourceOptionsByType: Record<EvidenceSourceType, string> = {
  sec: "SEC 文件",
  paper: "研究论文",
  patent: "专利",
  job: "公司招聘",
  company_update: "公司动态",
  social_discussion: "市场讨论"
};

export function createHttpEvidenceExplorerGateway(baseUrl: string): EvidenceExplorerGateway {
  return {
    async listEvidence(filters) {
      const params = new URLSearchParams({ limit: "500", theme: filters.theme });
      if (filters.sourceType !== "all") params.set("source_type", filters.sourceType);
      if (filters.company !== "all") params.set("company", filters.company);
      if (filters.dateRange !== "all") {
        const days = filters.dateRange === "30d" ? 30 : filters.dateRange === "90d" ? 90 : 365;
        params.set("date_from", new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10));
      }
      const response = await fetch(`${baseUrl}/api/evidence?${params.toString()}`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`证据接口返回 ${response.status}`);
      const payload = await response.json() as { evidence: ApiEvidenceEvent[] };
      const evidence = payload.evidence.map(mapApiEvent).sort((a, b) => b.publishedAt.localeCompare(a.publishedAt));
      return buildSnapshot(filters, evidence);
    },
    async getEvidence(evidenceId) {
      const response = await fetch(`${baseUrl}/api/evidence/${encodeURIComponent(evidenceId)}`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(response.status === 404 ? "证据不存在或已归档。" : `证据接口返回 ${response.status}`);
      return mapApiEvent(await response.json() as ApiEvidenceEvent);
    }
  };
}

const evidenceApiBaseUrl = process.env.NEXT_PUBLIC_EVIDENCE_API_BASE_URL?.replace(/\/$/, "") ?? "";
export const evidenceExplorerGateway = createHttpEvidenceExplorerGateway(evidenceApiBaseUrl);
