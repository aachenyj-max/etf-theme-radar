export type EvidenceSourceType = "sec" | "paper" | "patent" | "job" | "company_update" | "social_discussion";
export type EvidenceDateRange = "30d" | "90d" | "1y" | "all";
export type EvidenceLoadState = "idle" | "loading" | "ready" | "refreshing" | "empty" | "failed";
export type EvidenceDetailState = "closed" | "loading" | "ready" | "failed";
export type EvidenceConfidenceLevel = "high" | "medium" | "low";

export interface EvidenceExplorerFilters {
  sourceType: "all" | EvidenceSourceType;
  dateRange: EvidenceDateRange;
  company: string;
  theme: string;
}

export interface EvidenceRecord {
  id: string;
  sourceType: EvidenceSourceType;
  sourceLabel: string;
  publisher: string;
  publisherDomain: string;
  logoUrl: string;
  title: string;
  publishedAt: string;
  summary: string;
  qualityLabel: string;
  primaryOrSecondary: "primary" | "secondary";
  sourceQuality: number;
  confidence: number;
  originalUrl: string;
  extractedFacts: string[];
  relatedCompanies: string[];
  relatedThemes: Array<{ id: string; label: string }>;
}

export interface EvidenceSnapshot {
  state: "ready" | "empty";
  filters: EvidenceExplorerFilters;
  themeLabel: string;
  confidenceLevel: EvidenceConfidenceLevel;
  confidenceScore: number;
  primarySourceCount: number;
  sourceTypeCount: number;
  totalBeforeFilters: number;
  evidence: EvidenceRecord[];
  generatedAt: string;
}

export interface EvidenceExplorerGateway {
  listEvidence(filters: EvidenceExplorerFilters): Promise<EvidenceSnapshot>;
  getEvidence(evidenceId: string): Promise<EvidenceRecord>;
}

export const allowedEvidenceTransitions: Record<EvidenceLoadState, EvidenceLoadState[]> = {
  idle: ["loading"],
  loading: ["ready", "empty", "failed"],
  ready: ["refreshing"],
  refreshing: ["ready", "empty", "failed"],
  empty: ["refreshing"],
  failed: ["loading", "refreshing"]
};

export function canTransitionEvidence(from: EvidenceLoadState, to: EvidenceLoadState) {
  return allowedEvidenceTransitions[from].includes(to);
}

