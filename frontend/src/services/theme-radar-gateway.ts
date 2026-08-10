import type { ThemeOpportunity, ThemeRadarFilters, ThemeRadarGateway, ThemeRadarSnapshot } from "@/lib/theme-radar";

export const mockThemeOpportunities: ThemeOpportunity[] = [
  {
    id: "theme_ai_infrastructure",
    slug: "ai-infrastructure",
    title: "AI 基础设施",
    englishTitle: "AI Infrastructure",
    description: "算力、网络互连与数据中心基础设施需求持续增长。",
    sector: "technology",
    sources: ["sec", "research", "patents", "holdings", "careers", "market_discussion"],
    stage: "deep_research",
    trend: "emerging",
    metrics: { themeScore: 82, researchMomentum: 85, commercialAdoption: 76, etfWhiteSpace: 64, companies: 38 },
    latestCatalyst: "大型云服务商继续上调 AI 数据中心资本开支与电力需求预期。",
    latestEvidence: "SEC 文件、供应链招聘与光互连研究形成跨来源证据链。",
    mainRisk: "资本开支集中于少数公司，收入兑现与估值扩张可能不同步。",
    evidenceCount: 146,
    sourceTypeCount: 7,
    updatedAt: "12 分钟前"
  },
  {
    id: "theme_nuclear_energy",
    slug: "nuclear-energy",
    title: "核能与先进反应堆",
    englishTitle: "Nuclear Energy",
    description: "数据中心电力需求推动核电重启、SMR 与燃料链关注度回升。",
    sector: "energy",
    sources: ["sec", "research", "patents", "market_discussion"],
    stage: "validating",
    trend: "emerging",
    metrics: { themeScore: 78, researchMomentum: 81, commercialAdoption: 63, etfWhiteSpace: 72, companies: 24 },
    latestCatalyst: "科技公司签署长期核电采购协议，电力需求与建设周期开始对接。",
    latestEvidence: "监管文件与公司公告显示现有机组延寿和先进反应堆项目增加。",
    mainRisk: "审批、建设工期、燃料供应与项目融资仍构成长期约束。",
    evidenceCount: 94,
    sourceTypeCount: 5,
    updatedAt: "26 分钟前"
  },
  {
    id: "theme_robotics",
    slug: "robotics",
    title: "智能机器人",
    englishTitle: "Intelligent Robotics",
    description: "视觉模型、执行器和制造自动化正在推动机器人应用边界扩展。",
    sector: "industrials",
    sources: ["research", "patents", "careers", "holdings", "market_discussion"],
    stage: "validating",
    trend: "stable",
    metrics: { themeScore: 74, researchMomentum: 76, commercialAdoption: 68, etfWhiteSpace: 58, companies: 31 },
    latestCatalyst: "工业企业扩大具身智能试点，零部件厂商增加量产相关岗位。",
    latestEvidence: "专利、技术招聘与公司试点公告显示产业参与者数量上升。",
    mainRisk: "演示效果尚未充分转化为可重复订单和规模化收入。",
    evidenceCount: 108,
    sourceTypeCount: 6,
    updatedAt: "41 分钟前"
  },
  {
    id: "theme_edge_ai",
    slug: "edge-ai-infrastructure",
    title: "边缘 AI",
    englishTitle: "Edge AI",
    description: "端侧推理正在进入工业、汽车与消费设备，但商业化仍不均衡。",
    sector: "semiconductors",
    sources: ["research", "patents", "careers", "market_discussion"],
    stage: "emerging",
    trend: "emerging",
    metrics: { themeScore: 69, researchMomentum: 79, commercialAdoption: 61, etfWhiteSpace: 71, companies: 27 },
    latestCatalyst: "低功耗推理芯片与端侧模型发布频率上升。",
    latestEvidence: "论文和专利信号增强，但产品收入披露仍有限。",
    mainRisk: "通用 AI 叙事可能掩盖端侧应用的真实付费能力。",
    evidenceCount: 73,
    sourceTypeCount: 5,
    updatedAt: "1 小时前"
  },
  {
    id: "theme_grid_modernization",
    slug: "grid-modernization",
    title: "电网现代化",
    englishTitle: "Grid Modernization",
    description: "输配电瓶颈、数据中心接入与可再生能源并网推动设备更新。",
    sector: "industrials",
    sources: ["sec", "patents", "careers", "holdings"],
    stage: "deep_research",
    trend: "stable",
    metrics: { themeScore: 76, researchMomentum: 72, commercialAdoption: 81, etfWhiteSpace: 53, companies: 42 },
    latestCatalyst: "公用事业资本计划继续提高输电、变压器和电网软件投入。",
    latestEvidence: "公司文件和招聘数据支持订单周期延长，但来源集中度较高。",
    mainRisk: "监管回报机制、项目许可和设备交付周期可能限制增长速度。",
    evidenceCount: 121,
    sourceTypeCount: 5,
    updatedAt: "1 小时前"
  },
  {
    id: "theme_advanced_packaging",
    slug: "advanced-semiconductor-packaging",
    title: "先进半导体封装",
    englishTitle: "Advanced Packaging",
    description: "Chiplet、HBM 与高密度互连使先进封装成为算力扩张瓶颈。",
    sector: "semiconductors",
    sources: ["sec", "research", "patents", "careers", "holdings"],
    stage: "monitoring",
    trend: "cooling",
    metrics: { themeScore: 66, researchMomentum: 58, commercialAdoption: 79, etfWhiteSpace: 46, companies: 29 },
    latestCatalyst: "主要晶圆厂继续扩建先进封装产能，但新增公告速度放缓。",
    latestEvidence: "资本支出与招聘仍处高位，近期新增独立来源数量下降。",
    mainRisk: "现有半导体 ETF 已有较高暴露，产品空白可能有限。",
    evidenceCount: 87,
    sourceTypeCount: 5,
    updatedAt: "2 小时前"
  }
];

/** 生产版本在这里对接主题基线、评分和证据治理 API。 */
export const mockThemeRadarGateway: ThemeRadarGateway = {
  async listThemes(filters: ThemeRadarFilters): Promise<ThemeRadarSnapshot> {
    const themes = mockThemeOpportunities
      .filter((theme) => filters.sector === "all" || theme.sector === filters.sector)
      .filter((theme) => filters.source === "all" || theme.sources.includes(filters.source))
      .filter((theme) => filters.stage === "all" || theme.stage === filters.stage)
      .sort((a, b) => b.metrics.themeScore - a.metrics.themeScore);
    return {
      state: themes.length ? "ready" : "empty",
      filters,
      themes,
      candidates: [],
      totalBeforeFilters: mockThemeOpportunities.length,
      generatedAt: new Date().toISOString(),
      coverageNote: `${filters.period === "30d" ? "30 日" : filters.period === "90d" ? "90 日" : "1 年"}观察窗口 · 仅包含已治理证据`
    };
  },

  async getTheme(themeId) {
    const theme = mockThemeOpportunities.find((item) => item.id === themeId);
    if (!theme) throw new Error("主题不存在或已被归档。");
    return theme;
  },
  async reviewCandidate() { throw new Error("演示数据不支持候选复核。"); }
};

export const themeRadarGateway: ThemeRadarGateway = {
  async listThemes(filters) {
    const params = new URLSearchParams({ sector: filters.sector, source: filters.source, period: filters.period, stage: filters.stage });
    const response = await fetch(`/api/themes?${params.toString()}`, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`主题接口返回 ${response.status}`);
    const payload = await response.json() as Omit<ThemeRadarSnapshot, "state" | "filters">;
    return { ...payload, candidates: payload.candidates ?? [], state: payload.themes.length || payload.candidates?.length ? "ready" : "empty", filters };
  },
  async getTheme(themeId) {
    const response = await fetch(`/api/themes?period=1y`);
    if (!response.ok) throw new Error(`主题接口返回 ${response.status}`);
    const payload = await response.json() as { themes: ThemeOpportunity[] };
    const theme = payload.themes.find((item) => item.id === themeId || item.slug === themeId);
    if (!theme) throw new Error("主题不存在或尚无治理后证据。");
    return theme;
  },
  async reviewCandidate(candidateId, decision, targetThemeId = "") {
    const response = await fetch(`/api/theme-candidates/${encodeURIComponent(candidateId)}/review`, {
      method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ decision, target_theme_id: targetThemeId })
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      throw new Error(payload.detail ?? `候选复核接口返回 ${response.status}`);
    }
  }
};
