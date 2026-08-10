import type { MemoCitation, ReportDetailGateway, ReportMemoDetail, ReportVersionComparison, ReportVersionSummary } from "@/lib/report-detail";
import { mockReportLibraryGateway } from "@/services/report-library-gateway";

const sourceLogos = {
  sec: "https://www.sec.gov/files/sec-logo.png",
  company: "https://www.google.com/s2/favicons?domain=nvidia.com&sz=128",
  paper: "https://cdn.simpleicons.org/arxiv/B31B1B",
  patent: "https://cdn.simpleicons.org/google/4285F4",
  jobs: "https://cdn.simpleicons.org/greenhouse/357E63",
  discussion: "https://cdn.simpleicons.org/x/10273D"
};

const aiBullCase: MemoCitation[] = [
  {
    id: "citation-01",
    evidenceId: "EV-2026-0718",
    side: "bull",
    sourceType: "SEC 文件",
    publisher: "U.S. SEC",
    logoUrl: sourceLogos.sec,
    claim: "AI 基础设施投入正从单一加速器扩展到数据中心系统层。",
    evidence: "监管文件持续将加速计算、网络互连、电力和数据中心扩容列为资本配置重点，同时披露供电与交付周期约束。",
    limitation: "文件未单独披露 AI 基础设施业务收入，不能据此推导收入增速。",
    confidence: 0.96,
    url: "https://www.sec.gov/edgar/search/"
  },
  {
    id: "citation-02",
    evidenceId: "EV-2026-0709",
    side: "bull",
    sourceType: "公司公告",
    publisher: "NVIDIA Newsroom",
    logoUrl: sourceLogos.company,
    claim: "竞争边界正在从芯片转向机架级计算系统。",
    evidence: "公司更新将加速器、网络互连、机架设计与软件栈放入同一产品架构，显示系统级集成的重要性提高。",
    limitation: "产品发布不等于客户部署、订单确认或收入兑现。",
    confidence: 0.93,
    url: "https://nvidianews.nvidia.com/"
  },
  {
    id: "citation-03",
    evidenceId: "EV-2026-0694",
    side: "bull",
    sourceType: "学术论文",
    publisher: "arXiv",
    logoUrl: sourceLogos.paper,
    claim: "带宽、延迟与能耗正在成为推理集群扩展的共同瓶颈。",
    evidence: "研究比较大规模推理集群中的互连架构，指出算力扩展需要同步解决网络带宽与能源效率问题。",
    limitation: "学术可行性不能直接证明商业采用和单位经济性。",
    confidence: 0.91,
    url: "https://arxiv.org/search/?query=optical+interconnect+AI+clusters&searchtype=all"
  },
  {
    id: "citation-04",
    evidenceId: "EV-2026-0672",
    side: "bull",
    sourceType: "公开专利",
    publisher: "Google Patents",
    logoUrl: sourceLogos.patent,
    claim: "高密度计算正在形成持续的热管理研发投入。",
    evidence: "相关专利族覆盖液冷回路、机架热管理和模块化部署，工程投入不再局限于计算芯片。",
    limitation: "专利数量不能单独证明产品差异化或可实现收入。",
    confidence: 0.88,
    url: "https://patents.google.com/?q=(AI+data+center+cooling)"
  }
];

const aiBearCase: MemoCitation[] = [
  {
    id: "citation-05",
    evidenceId: "EV-2026-0617",
    side: "bear",
    sourceType: "市场讨论",
    publisher: "X / Industry Analysts",
    logoUrl: sourceLogos.discussion,
    claim: "市场叙事可能提前反映尚未兑现的电力与网络需求。",
    evidence: "市场讨论高度集中在电力、变压器和光互连瓶颈，但许多陈述尚未获得订单、收入或项目级一级来源验证。",
    limitation: "社交讨论仅用于发现问题，不作为高置信度事实。",
    confidence: 0.68,
    url: "https://x.com/search?q=AI%20data%20center%20power%20networking&src=typed_query"
  }
];

function buildAiMemo(asset: Awaited<ReturnType<typeof mockReportLibraryGateway.getReport>>): ReportMemoDetail {
  return {
    reportId: asset.id,
    runId: asset.runId,
    title: asset.title,
    themeId: asset.themeId,
    themeLabel: asset.themeLabel,
    status: "DEEP_RESEARCH",
    confidence: "high",
    lastUpdated: asset.updatedAt,
    version: asset.version,
    auditPassed: asset.auditPassed,
    conclusion: {
      verdict: "mixed",
      confidence: "medium",
      statement: "现有证据同时显示基础设施需求扩散与商业兑现约束，适合继续深度研究。",
      keyEvidenceIds: ["sec-nvda-10k", "openalex-photonics"],
      limitations: ["ETF 持仓与资金流仍待一级来源核验。"],
      modelUsed: true
    },
    executiveSummary: "AI 计算需求正在向网络互连、电力、冷却和机架级系统扩散，主题证据已不再局限于 GPU 供给。当前跨来源证据足以支持深度研究，但尚不足以形成 ETF 产品或投资结论。",
    investmentThesis: "如果训练与推理需求持续增长，价值捕获可能从加速器向网络、电力、热管理和数据中心部署环节扩散；主题机会的关键不在于 AI 叙事本身，而在于这些基础设施约束能否转化为可验证的订单、收入与上市公司盈利。",
    whyNow: [
      "云服务商资本开支继续强调 AI 数据中心与网络能力。",
      "系统设计从单一芯片转向机架、互连、电力与冷却协同。",
      "论文、专利和技术岗位对基础设施瓶颈形成跨来源印证。"
    ],
    keyDrivers: [
      "训练与推理集群规模扩大带来的网络带宽需求",
      "高密度机架对供电、液冷和热管理的增量要求",
      "数据中心建设周期与电网接入能力",
      "云服务商和企业客户的持续资本投入"
    ],
    mainRisks: [
      "资本开支集中于少数大型客户，需求可能出现阶段性波动",
      "基础设施订单、交付和收入确认存在时间差",
      "估值扩张可能早于盈利兑现",
      "现有半导体和科技 ETF 已包含大量相关暴露"
    ],
    bullCase: aiBullCase,
    bearCase: {
      citations: aiBearCase,
      counterArguments: [
        "基础设施瓶颈可能通过效率提升而非持续扩产解决。",
        "云服务商资本开支增长未必传导至全部供应链公司。",
        "主题定义过宽可能导致公司池与现有科技 ETF 高度重合。"
      ],
      risks: [
        "客户和供应商集中度较高",
        "电力审批与数据中心建设周期延长",
        "订单能见度与最终收入确认不一致"
      ],
      missingData: [
        "完整的上市公司收入暴露映射",
        "连续 90 日主题历史基线",
        "现有 ETF 持仓重叠与集中度",
        "已完成的系统性反方证据检索"
      ]
    },
    etfLandscape: {
      existingEtfs: ["现有半导体 ETF", "云计算与数据中心 REIT ETF", "电力基础设施 ETF"],
      overlap: "现有产品分别覆盖芯片、数据中心地产和电力设备，但跨环节持仓重叠尚未完成统一测算。",
      whiteSpace: "unknown：在完成持仓穿透与竞争产品样本前，不判断产品空白。",
      dataStatus: "partial"
    },
    companyMap: {
      purePlays: [],
      enablers: ["加速计算与网络设备供应商", "电源与液冷设备供应商", "光互连与数据中心部署服务商"],
      beneficiaries: ["云服务商", "数据中心运营商", "公用事业与输配电设备公司"],
      dataStatus: "partial"
    },
    decision: {
      currentStatus: "DEEP_RESEARCH",
      rationale: "来源质量与多样性已达到深度研究门槛，但反方检索、上市公司映射、历史基线和 ETF 持仓重叠仍不完整。",
      nextActions: [
        "完成现有 ETF 持仓穿透与重叠测算",
        "建立上市公司 AI 基础设施收入暴露映射",
        "补充反方证据并验证资本开支向收入的传导",
        "积累至少 90 日历史基线后复核主题动量"
      ]
    }
  };
}

function buildFallbackMemo(asset: Awaited<ReturnType<typeof mockReportLibraryGateway.getReport>>): ReportMemoDetail {
  const status = asset.status === "deep_research" ? "DEEP_RESEARCH" : asset.status === "watch" ? "WATCH" : "WATCH";
  return {
    reportId: asset.id,
    runId: asset.runId,
    title: asset.title,
    themeId: asset.themeId,
    themeLabel: asset.themeLabel,
    status,
    confidence: asset.auditPassed ? "medium" : "low",
    lastUpdated: asset.updatedAt,
    version: asset.version,
    auditPassed: asset.auditPassed,
    conclusion: {
      verdict: "insufficient",
      confidence: "low",
      statement: "当前结构化证据不足，尚不能形成稳健主题结论。",
      keyEvidenceIds: [],
      limitations: ["等待研究任务生成受控证据结论。"],
      modelUsed: false
    },
    executiveSummary: asset.summary,
    investmentThesis: "该报告已进入资料库，但结构化投资委员会章节仍需由对应研究任务补齐。",
    whyNow: ["当前存在值得持续跟踪的公开信息信号。"],
    keyDrivers: ["独立一级来源的持续新增。"],
    mainRisks: ["当前结构化证据不足，不能形成投资或产品结论。"],
    bullCase: [],
    bearCase: { citations: [], counterArguments: [], risks: ["缺少完整反方证据。"], missingData: ["结构化报告详情尚未生成。"] },
    etfLandscape: { existingEtfs: [], overlap: "unknown", whiteSpace: "unknown", dataStatus: "unknown" },
    companyMap: { purePlays: [], enablers: [], beneficiaries: [], dataStatus: "unknown" },
    decision: { currentStatus: status, rationale: "等待结构化证据和审计结果补齐。", nextActions: ["重新运行对应主题研究任务。"] }
  };
}

export const mockReportDetailGateway: ReportDetailGateway = {
  async getReportDetail(reportId) {
    const asset = await mockReportLibraryGateway.getReport(reportId);
    return asset.id === "report_ai_infrastructure" ? buildAiMemo(asset) : buildFallbackMemo(asset);
  },
  async getTimeline(reportId) { return { report_id: reportId, versions: [] }; },
  async compareVersions(reportId, left, right) { return { report_id: reportId, left, right, added: [], removed: [], unchanged_count: 0, structured: { conclusion: { before: "", after: "", changed: false }, score_changes: [], etfs_added: [], etfs_removed: [], evidence_gaps_added: [], evidence_gaps_closed: [], evidence_count_before: 0, evidence_count_after: 0 } }; },
  async refreshMarketSnapshot() { return { runId: "mock-market-refresh" }; }
};

export function createHttpReportDetailGateway(baseUrl: string): ReportDetailGateway {
  return {
    async getReportDetail(reportId, version) {
      const query = version ? `?version=${version}` : "";
      const response = await fetch(`${baseUrl}/api/reports/${encodeURIComponent(reportId)}/detail${query}`, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        const error = new Error(response.status === 404 ? "报告不存在或已经删除。" : `报告详情接口返回 ${response.status}`) as Error & { status?: number };
        error.status = response.status;
        throw error;
      }
      return await response.json() as ReportMemoDetail;
    },
    async getTimeline(reportId) {
      const response = await fetch(`${baseUrl}/api/reports/${encodeURIComponent(reportId)}/timeline`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`报告时间线接口返回 ${response.status}`);
      return await response.json() as { report_id: string; versions: ReportVersionSummary[] };
    },
    async compareVersions(reportId, left, right) {
      const response = await fetch(`${baseUrl}/api/reports/${encodeURIComponent(reportId)}/compare?left=${left}&right=${right}`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`报告版本比较接口返回 ${response.status}`);
      return await response.json() as ReportVersionComparison;
    },
    async refreshMarketSnapshot(reportId) {
      const response = await fetch(`${baseUrl}/api/reports/${encodeURIComponent(reportId)}/market-snapshot`, { method: "POST" });
      if (!response.ok) throw new Error(`市场快照刷新接口返回 ${response.status}`);
      const payload = await response.json() as { run_id: string };
      return { runId: payload.run_id };
    }
  };
}

const reportApiBaseUrl = process.env.NEXT_PUBLIC_REPORTS_API_BASE_URL?.replace(/\/$/, "") ?? "";
export const reportDetailGateway = createHttpReportDetailGateway(reportApiBaseUrl);
