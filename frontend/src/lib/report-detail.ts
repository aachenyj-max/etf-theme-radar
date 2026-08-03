export type ReportDetailLoadState = "idle" | "loading" | "ready" | "refreshing" | "failed" | "not_found";
export type MemoDecisionStatus = "WATCH" | "DEEP_RESEARCH" | "REJECT";
export type MemoConfidence = "high" | "medium" | "low";
export type MemoEvidenceSide = "bull" | "bear";

export interface MemoCitation {
  id: string;
  evidenceId: string;
  side: MemoEvidenceSide;
  sourceType: string;
  publisher: string;
  logoUrl: string;
  claim: string;
  evidence: string;
  limitation: string;
  confidence: number;
  url: string;
}

export interface CounterArgument {
  claim: string;
  reason: string;
  sourceUrl: string;
  publisher: string;
}

export interface EtfMarketProduct {
  ticker: string;
  yahoo_symbol?: string;
  fund_name?: string;
  issuer: string;
  category: string;
  exchange?: string;
  listing_market?: string;
  official_url: string;
  source_url: string;
  data_status: "available" | "partial" | "stale" | "unavailable" | "insufficient_data";
  as_of?: string;
  last_close?: number;
  currency?: string;
  returns?: { "1w"?: number | null; "1m"?: number | null; "3m"?: number | null };
  annualized_volatility_3m?: number | null;
  max_drawdown_3m?: number | null;
  average_dollar_volume_20d?: number | null;
  volume_activity_ratio?: number | null;
  activity_trend?: "higher" | "lower" | "stable";
  price_trend?: "up" | "down" | "sideways";
  relative_strength_1m?: number | null;
  error?: string;
}

export interface ReportMemoDetail {
  reportId: string;
  runId?: string;
  title: string;
  themeId: string;
  themeLabel: string;
  status: MemoDecisionStatus;
  confidence: MemoConfidence;
  lastUpdated: string;
  version: number;
  auditPassed: boolean;
  conclusion: {
    verdict: "supported" | "mixed" | "insufficient";
    confidence: MemoConfidence;
    statement: string;
    keyEvidenceIds: string[];
    limitations: string[];
    modelUsed: boolean;
  };
  executiveSummary: string;
  investmentThesis: string;
  whyNow: string[];
  keyDrivers: string[];
  mainRisks: string[];
  bullCase: MemoCitation[];
  bearCase: {
    citations: MemoCitation[];
    counterArguments: Array<CounterArgument | string>;
    risks: string[];
    missingData: string[];
  };
  etfLandscape: {
    existingEtfs: string[];
    overlap: string;
    whiteSpace: string;
    dataStatus: "available" | "partial" | "unknown";
    products?: EtfMarketProduct[];
    marketAsOf?: string;
    marketSnapshotStatus?: "available" | "partial" | "unknown";
    limitations?: string[];
  };
  latestMarketSnapshot?: {
    snapshot_id?: string;
    origin: "independent_snapshot" | "legacy_report_snapshot" | "unavailable";
    collected_at?: string;
    market_as_of?: string;
    status?: "available" | "partial" | "unknown";
    products?: EtfMarketProduct[];
    limitations?: string[];
    errors?: Array<{ ticker?: string; error?: string }>;
  };
  researchSources?: Array<{
    id: string;
    name: string;
    type: string;
    citationCount: number;
    url: string;
    logoUrl: string;
    fallback: string;
  }>;
  companyMap: {
    purePlays: string[];
    enablers: string[];
    beneficiaries: string[];
    dataStatus: "available" | "partial" | "unknown";
  };
  decision: {
    currentStatus: MemoDecisionStatus;
    rationale: string;
    nextActions: string[];
  };
}

export interface ReportDetailGateway {
  getReportDetail(reportId: string): Promise<ReportMemoDetail>;
  refreshMarketSnapshot(reportId: string): Promise<{ runId: string }>;
}

export const allowedReportDetailTransitions: Record<ReportDetailLoadState, ReportDetailLoadState[]> = {
  idle: ["loading"],
  loading: ["ready", "failed", "not_found"],
  ready: ["refreshing"],
  refreshing: ["ready", "failed", "not_found"],
  failed: ["loading", "refreshing"],
  not_found: ["loading"]
};

export function canTransitionReportDetail(from: ReportDetailLoadState, to: ReportDetailLoadState) {
  return allowedReportDetailTransitions[from].includes(to);
}
