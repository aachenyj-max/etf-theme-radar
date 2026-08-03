export type ResearchObjective =
  | "discover_emerging_themes"
  | "analyze_etf_landscape"
  | "track_industry_momentum"
  | "build_investment_thesis";

export type IntelligenceSourceId =
  | "sec"
  | "arxiv"
  | "patents"
  | "etf_holdings"
  | "etf_news"
  | "company_careers"
  | "sp_global"
  | "x"
  | "forums";

export type ResearchTimeRange = "30d" | "90d" | "1y" | "custom";
export type ResearchOutputType = "quick_scan" | "theme_report" | "etf_opportunity_analysis";

export interface CustomDateRange {
  from: string;
  to: string;
}

export interface ResearchDraft {
  topic: string;
  objective: ResearchObjective;
  sources: IntelligenceSourceId[];
  timeRange: ResearchTimeRange;
  customDateRange?: CustomDateRange;
  outputType: ResearchOutputType;
}

export type ResearchRunState =
  | "draft"
  | "validating"
  | "submitting"
  | "waiting"
  | "planning"
  | "awaiting_theme_review"
  | "queued"
  | "collecting"
  | "governing"
  | "analyzing"
  | "auditing"
  | "awaiting_report_review"
  | "completed"
  | "returned"
  | "cancelled"
  | "blocked_configuration"
  | "failed";

export interface AgentRunAudit {
  agentRunId: string;
  provider: string;
  model: string;
  status: string;
  stopReason?: string;
  modelRequests: number;
  toolCalls: number;
  inputTokens: number;
  outputTokens: number;
}

export interface ToolCallAudit {
  id: number;
  name: string;
  status: string;
  latencyMs: number;
  evidenceDelta: number;
  relevantEvidenceDelta?: number;
  error?: string;
  currentSource?: string;
  cacheStatus?: string;
}

export interface RunStepAudit {
  name: string;
  status: string;
  startedAt?: string;
  finishedAt?: string;
  error?: string;
}
export interface ApprovalAudit { gate: string; decision: string; note: string; createdAt: string; }

export type StreamConnectionState = "connecting" | "live" | "reconnecting" | "polling" | "closed";

export interface ResearchRunSnapshot {
  runId: string;
  state: ResearchRunState;
  progress: number;
  stageLabel: string;
  createdAt: string;
  updatedAt: string;
  error?: string;
}

export interface ResearchRunRecord extends ResearchRunSnapshot {
  request: ResearchDraft;
  reviewGate?: "theme_definition" | "final_report" | "";
  result?: {
    theme_definition?: { theme_id: string; name: string; description: string; aliases: string[]; research_questions: string[]; model_used: boolean };
    available_actions?: string[];
    report_markdown?: string;
  };
  agentRuns?: AgentRunAudit[];
  toolCalls?: ToolCallAudit[];
  steps?: RunStepAudit[];
  approvals?: ApprovalAudit[];
  evidenceProgress?: { baseline: number; current: number; rawAdded: number; relevantAdded: number };
  queuePosition?: number | null;
  needsAttention?: boolean;
  auditSummary?: {
    researchObjective: string;
    coverage: { baseline: number; current: number; raw_added?: number; relevant_added?: number };
    counterCheck: boolean;
    remainingGaps: string[];
    stopReason: string;
    usage: { modelRequests: number; toolCalls: number };
  };
}

export interface ResearchRunListItem {
  runId: string;
  topic: string;
  state: ResearchRunState;
  stage: string;
  progress: number;
  createdAt: string;
  updatedAt: string;
  queuePosition?: number | null;
  needsAttention: boolean;
  outputType: ResearchOutputType;
}

export interface ResearchWorkflowGateway {
  createRun(request: ResearchDraft): Promise<ResearchRunRecord>;
  getRun(runId: string): Promise<ResearchRunRecord>;
  subscribeRun(runId: string, handlers: { onSnapshot: (run: ResearchRunRecord) => void; onConnectionChange: (state: StreamConnectionState) => void; onError: (error: Error) => void }): () => void;
  cancelRun(runId: string): Promise<ResearchRunRecord>;
  reviewTheme(runId: string, decision: "approve" | "return", note?: string): Promise<ResearchRunRecord>;
  reviewReport(runId: string, decision: "approve" | "return", note?: string): Promise<ResearchRunRecord>;
  rerun(runId: string): Promise<ResearchRunRecord>;
  finish(runId: string): Promise<void>;
  listRuns(limit?: number, offset?: number): Promise<{ runs: ResearchRunListItem[]; total: number; hasMore: boolean }>;
}

export const allowedResearchTransitions: Record<ResearchRunState, ResearchRunState[]> = {
  draft: ["validating"],
  validating: ["submitting", "failed"],
  submitting: ["planning", "queued", "failed"],
  waiting: ["planning", "cancelled"],
  planning: ["awaiting_theme_review", "failed"],
  awaiting_theme_review: ["queued", "returned", "cancelled"],
  queued: ["collecting", "failed"],
  collecting: ["governing", "failed"],
  governing: ["analyzing", "failed"],
  analyzing: ["auditing", "failed"],
  auditing: ["awaiting_report_review", "failed"],
  awaiting_report_review: ["completed", "returned", "cancelled"],
  completed: [],
  returned: ["planning", "queued"],
  cancelled: [],
  failed: [],
  blocked_configuration: []
};

export function canTransitionResearchRun(from: ResearchRunState, to: ResearchRunState) {
  return allowedResearchTransitions[from].includes(to);
}

export function validateResearchDraft(draft: ResearchDraft) {
  const errors: Partial<Record<"topic" | "sources" | "customDateRange", string>> = {};
  if (draft.topic.trim().length < 2) errors.topic = "请输入至少两个字符的研究主题。";
  if (draft.sources.length === 0) errors.sources = "请至少选择一个情报来源。";
  if (draft.timeRange === "custom") {
    if (!draft.customDateRange?.from || !draft.customDateRange?.to) {
      errors.customDateRange = "请选择完整的开始和结束日期。";
    } else if (draft.customDateRange.from > draft.customDateRange.to) {
      errors.customDateRange = "开始日期不能晚于结束日期。";
    }
  }
  return errors;
}

export function isResearchDraftValid(draft: ResearchDraft) {
  return Object.keys(validateResearchDraft(draft)).length === 0;
}
