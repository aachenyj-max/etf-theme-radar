export type ThemeSector = "all" | "technology" | "industrials" | "energy" | "semiconductors";
export type ThemeSource = "all" | "sec" | "research" | "patents" | "holdings" | "careers" | "market_discussion";
export type ThemeTimePeriod = "30d" | "90d" | "1y";
export type ThemeStage = "all" | "emerging" | "validating" | "deep_research" | "monitoring";
export type ThemeTrend = "emerging" | "stable" | "cooling" | "unknown";
export type ThemeRadarLoadState = "idle" | "loading" | "ready" | "refreshing" | "empty" | "failed";

export interface ThemeRadarFilters {
  sector: ThemeSector;
  source: ThemeSource;
  period: ThemeTimePeriod;
  stage: ThemeStage;
}

export interface ThemeSignalMetrics {
  themeScore: number;
  researchMomentum: number;
  commercialAdoption: number;
  etfWhiteSpace: number;
  companies: number;
}

export interface ThemeOpportunity {
  id: string;
  slug: string;
  title: string;
  englishTitle: string;
  description: string;
  sector: Exclude<ThemeSector, "all">;
  sources: Array<Exclude<ThemeSource, "all">>;
  stage: Exclude<ThemeStage, "all">;
  trend: ThemeTrend;
  metrics: ThemeSignalMetrics;
  latestCatalyst: string;
  latestEvidence: string;
  mainRisk: string;
  evidenceCount: number;
  sourceTypeCount: number;
  updatedAt: string;
  currentConclusion?: string;
  reportVersion?: number;
  lastVerifiedAt?: string;
  reportId?: string;
  trendReason?: string;
  coverage?: { evidence: number; sourceTypes: number; official: number; confidence: string };
  coverageGaps?: Array<{ kind: string; reason: string; next_path: string; updated_at: string }>;
  timeline?: Array<{ evidence_id: string; title: string; occurred_at: string; source: string }>;
}

export type ThemeCandidateStatus = "signal" | "validating" | "awaiting_confirmation" | "confirmed" | "merged" | "rejected";
export interface ThemeCandidateMetrics {
  evidence_count: number; publisher_count: number; source_type_count: number; entity_count: number;
  official_count: number; acceleration: number; gate_passed: boolean; confirmation_gate_passed: boolean;
  visualization_blocks: {
    evidence_timeline: Array<{ date: string; count: number }>;
    source_diffusion: Array<{ source_type: string; count: number }>;
    entity_coverage: Array<{ label: string; count: number }>;
    etf_coverage: { status: "observed" | "not_assessed"; evidence_count: number; note: string };
  };
}
export interface ThemeCandidate {
  candidate_id: string; proposed_name: string; description: string; status: ThemeCandidateStatus;
  rationale: string; first_seen_at: string; last_seen_at: string; metrics: ThemeCandidateMetrics;
  aliases: string[]; entities: Array<{ label: string; entity_type: string; mention_count: number }>;
  evidence: Array<{ event_id: string; title: string; publisher?: string; source_type: string; published_at?: string }>;
}

export interface ThemeRadarSnapshot {
  state: Exclude<ThemeRadarLoadState, "idle" | "loading" | "refreshing" | "failed">;
  filters: ThemeRadarFilters;
  themes: ThemeOpportunity[];
  candidates: ThemeCandidate[];
  totalBeforeFilters: number;
  generatedAt: string;
  coverageNote: string;
}

export interface ThemeRadarGateway {
  listThemes(filters: ThemeRadarFilters): Promise<ThemeRadarSnapshot>;
  getTheme(themeId: string): Promise<ThemeOpportunity>;
  reviewCandidate(candidateId: string, decision: "confirm" | "merge" | "reject", targetThemeId?: string): Promise<void>;
}

export const allowedRadarTransitions: Record<ThemeRadarLoadState, ThemeRadarLoadState[]> = {
  idle: ["loading"],
  loading: ["ready", "empty", "failed"],
  ready: ["refreshing"],
  refreshing: ["ready", "empty", "failed"],
  empty: ["refreshing"],
  failed: ["loading", "refreshing"]
};

export function canTransitionRadar(from: ThemeRadarLoadState, to: ThemeRadarLoadState) {
  return allowedRadarTransitions[from].includes(to);
}
