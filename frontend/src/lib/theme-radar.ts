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
}

export interface ThemeRadarSnapshot {
  state: Exclude<ThemeRadarLoadState, "idle" | "loading" | "refreshing" | "failed">;
  filters: ThemeRadarFilters;
  themes: ThemeOpportunity[];
  totalBeforeFilters: number;
  generatedAt: string;
  coverageNote: string;
}

export interface ThemeRadarGateway {
  listThemes(filters: ThemeRadarFilters): Promise<ThemeRadarSnapshot>;
  getTheme(themeId: string): Promise<ThemeOpportunity>;
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
