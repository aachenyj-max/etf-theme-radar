export type ReportFolderId = "all" | "ai" | "energy" | "robotics" | "healthcare";
export type ReportStatus = "deep_research" | "watch" | "completed" | "draft" | "archived";
export type ReportKind = "theme_report" | "quick_scan" | "etf_opportunity_analysis" | "event_report" | "landscape_scan" | "evidence_brief";
export type ReportDateRange = "30d" | "90d" | "1y" | "all";
export type ReportLibraryLoadState = "idle" | "loading" | "ready" | "refreshing" | "empty" | "failed";
export type ReportMutationAction = "renaming" | "archiving" | "deleting";
export type ReportAssistantState = "closed" | "idle" | "running" | "ready" | "failed";

export interface ReportLibraryFilters {
  query: string;
  folder: ReportFolderId;
  status: "all" | ReportStatus;
  dateRange: ReportDateRange;
}

export interface ResearchReportAsset {
  id: string;
  runId?: string;
  title: string;
  kind: ReportKind;
  themeId: string;
  themeLabel: string;
  folder: Exclude<ReportFolderId, "all">;
  status: ReportStatus;
  tags: string[];
  summary: string;
  updatedAt: string;
  createdAt: string;
  version: number;
  sourceCount: number;
  evidenceCount: number;
  auditPassed: boolean;
}

export interface ReportFolderSummary {
  id: Exclude<ReportFolderId, "all">;
  label: string;
  englishLabel: string;
  reportCount: number;
  latestUpdate?: string;
}

export interface ReportLibrarySnapshot {
  state: "ready" | "empty";
  reports: ResearchReportAsset[];
  folders: ReportFolderSummary[];
  totalBeforeFilters: number;
  activeCount: number;
  archivedCount: number;
  generatedAt: string;
}

export interface ReportAssistantResult {
  title: string;
  summary: string;
  matchedReportIds: string[];
  suggestedFilters?: Partial<ReportLibraryFilters>;
}

export interface ReportLibraryGateway {
  listReports(filters: ReportLibraryFilters): Promise<ReportLibrarySnapshot>;
  getReport(reportId: string): Promise<ResearchReportAsset>;
  renameReport(reportId: string, title: string): Promise<ResearchReportAsset>;
  archiveReport(reportId: string): Promise<ResearchReportAsset>;
  deleteReport(reportId: string): Promise<void>;
  askLibrary(command: string): Promise<ReportAssistantResult>;
}

export const allowedReportLibraryTransitions: Record<ReportLibraryLoadState, ReportLibraryLoadState[]> = {
  idle: ["loading"],
  loading: ["ready", "empty", "failed"],
  ready: ["refreshing"],
  refreshing: ["ready", "empty", "failed"],
  empty: ["refreshing"],
  failed: ["loading", "refreshing"]
};

export function canTransitionReportLibrary(from: ReportLibraryLoadState, to: ReportLibraryLoadState) {
  return allowedReportLibraryTransitions[from].includes(to);
}
