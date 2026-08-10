import type { ResearchDraft, ResearchRunListItem, ResearchRunRecord, ResearchRunState, ResearchWorkflowGateway } from "@/lib/research-workflow";
import { labelFor, statusLabels, toolLabels } from "@/lib/ui-labels";

const stateTimeline: Array<{ state: ResearchRunState; progress: number; stageLabel: string; afterMs: number }> = [
  { state: "queued", progress: 8, stageLabel: "任务已进入研究队列", afterMs: 0 },
  { state: "collecting", progress: 28, stageLabel: "正在采集所选信息源", afterMs: 1800 },
  { state: "governing", progress: 52, stageLabel: "正在去重并治理证据", afterMs: 3800 },
  { state: "analyzing", progress: 74, stageLabel: "正在形成主题研究结论", afterMs: 6000 },
  { state: "auditing", progress: 91, stageLabel: "正在审计引用与事实", afterMs: 8200 },
  { state: "completed", progress: 100, stageLabel: "研究任务已完成", afterMs: 10400 }
];

const mockRuns = new Map<string, ResearchRunRecord>();

/**
 * 前端演示网关。生产接入时以 HTTP 实现替换该实例，页面和状态机无需改动。
 * 对应后端接口：POST /api/research-runs、GET /api/research-runs/{run_id}。
 */
export const mockResearchWorkflowGateway: ResearchWorkflowGateway = {
  async createRun(request) {
    const now = new Date();
    const runId = `rr_${now.getTime().toString(36)}`;
    const record: ResearchRunRecord = {
      runId,
      request,
      state: "queued",
      progress: 8,
      stageLabel: "任务已进入研究队列",
      createdAt: now.toISOString(),
      updatedAt: now.toISOString()
    };
    mockRuns.set(runId, record);
    return record;
  },

  async getRun(runId) {
    const record = mockRuns.get(runId);
    if (!record) throw new Error("研究任务不存在或已经过期。");
    const elapsed = Date.now() - new Date(record.createdAt).getTime();
    const stage = [...stateTimeline].reverse().find((item) => elapsed >= item.afterMs) ?? stateTimeline[0];
    const updated = { ...record, ...stage, updatedAt: new Date().toISOString() };
    mockRuns.set(runId, updated);
    return updated;
  },

  subscribeRun(runId, handlers) {
    handlers.onConnectionChange("live");
    const timer = window.setInterval(() => {
      void this.getRun(runId).then(handlers.onSnapshot).catch((reason) => handlers.onError(reason instanceof Error ? reason : new Error("研究状态读取失败")));
    }, 1000);
    return () => { window.clearInterval(timer); handlers.onConnectionChange("closed"); };
  },

  async cancelRun(runId) {
    const record = mockRuns.get(runId);
    if (!record) throw new Error("研究任务不存在或已经过期。");
    const updated: ResearchRunRecord = {
      ...record,
      state: "failed",
      stageLabel: "任务已由用户停止",
      error: "用户停止了本次演示任务。",
      updatedAt: new Date().toISOString()
    };
    mockRuns.set(runId, updated);
    return updated;
  },
  async reviewTheme(runId, decision) {
    const record = await this.getRun(runId);
    return { ...record, state: decision === "approve" ? "queued" : "returned", stageLabel: decision === "approve" ? "等待执行" : "主题定义已退回" };
  },
  async reviewReport(runId, decision) {
    const record = await this.getRun(runId);
    return { ...record, state: decision === "approve" ? "completed" : "returned", stageLabel: decision === "approve" ? "报告已通过" : "报告已退回" };
  },
  async rerun(runId) {
    const record = await this.getRun(runId);
    return { ...record, state: "queued", stageLabel: "任务已重新排队" };
  },
  async finish(runId) { mockRuns.delete(runId); },
  async listRuns() {
    const runs: ResearchRunListItem[] = [...mockRuns.values()].map((run) => ({
      runId: run.runId, topic: run.request.topic, state: run.state, stage: run.stageLabel,
      progress: run.progress, createdAt: run.createdAt, updatedAt: run.updatedAt,
      queuePosition: run.queuePosition, needsAttention: Boolean(run.needsAttention),
      outputType: run.request.outputType
    }));
    return { runs, total: runs.length, hasMore: false };
  },
};

type ApiRun = {
  run_id: string;
  status: ResearchRunState;
  stage: string;
  progress: number;
  created_at: string;
  updated_at: string;
  request: ResearchDraft;
  result?: ResearchRunRecord["result"];
  review_gate?: ResearchRunRecord["reviewGate"];
  error?: string;
  agent_runs?: Array<{ agent_run_id: string; provider: string; model: string; status: string; stop_reason?: string; model_requests: number; tool_calls: number; input_tokens: number; output_tokens: number }>;
  tool_calls?: Array<{ tool_call_id: number; tool_name: string; status: string; latency_ms: number; evidence_delta: number; relevant_evidence_delta?: number; error?: string; arguments?: { source?: string }; result?: { cache_status?: string; cached?: boolean } }>;
  steps?: Array<{ step_name: string; status: string; started_at?: string; finished_at?: string; error?: string }>;
  approvals?: Array<{ gate: string; decision: string; note: string; created_at: string }>;
  evidence_progress?: { baseline: number; current: number; raw_added: number; relevant_added: number };
  queue_position?: number | null;
  needs_attention?: boolean;
  audit_summary?: ResearchRunRecord["auditSummary"];
};

function mapRun(item: ApiRun): ResearchRunRecord {
  const labels: Record<string, string> = {
    planning: "正在定义主题与研究边界",
    theme_review: "等待确认主题定义",
    collecting: "正在读取所选公开来源",
    governing: "正在治理、去重与分类证据",
    analyzing: "正在形成受证据约束的研究报告",
    report_review: "等待复核最终报告",
    completed: "研究任务已完成",
    returned: "任务已退回",
    cancelled: "任务已取消",
    blocked_configuration: "模型配置需要修复",
    failed: "任务运行失败"
  };
  return {
    runId: item.run_id,
    request: item.request,
    state: item.status,
    progress: item.progress ?? 0,
    stageLabel: labels[item.stage] ?? item.stage,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    error: item.error || undefined,
    reviewGate: item.review_gate,
    result: item.result,
    agentRuns: (item.agent_runs ?? []).map((run) => ({ agentRunId: run.agent_run_id, provider: run.provider, model: run.model, status: run.status, stopReason: run.stop_reason, modelRequests: run.model_requests, toolCalls: run.tool_calls, inputTokens: run.input_tokens, outputTokens: run.output_tokens })),
    toolCalls: (item.tool_calls ?? []).map((call) => ({ id: call.tool_call_id, name: labelFor(toolLabels, call.tool_name), status: labelFor(statusLabels, call.status), latencyMs: call.latency_ms, evidenceDelta: call.evidence_delta, relevantEvidenceDelta: call.relevant_evidence_delta ?? 0, error: call.error || undefined, currentSource: call.arguments?.source, cacheStatus: call.result?.cache_status === "hit" ? "命中缓存" : call.result?.cache_status === "mixed" ? "部分缓存" : call.result?.cache_status === "miss" ? "实时获取" : (call.result?.cached ? "命中缓存" : undefined) })),
    steps: (item.steps ?? []).map((step) => ({ name: step.step_name, status: step.status, startedAt: step.started_at, finishedAt: step.finished_at, error: step.error || undefined }))
    ,approvals: (item.approvals ?? []).map((approval) => ({ gate: approval.gate, decision: approval.decision, note: approval.note, createdAt: approval.created_at })),
    evidenceProgress: item.evidence_progress ? { baseline: item.evidence_progress.baseline, current: item.evidence_progress.current, rawAdded: item.evidence_progress.raw_added, relevantAdded: item.evidence_progress.relevant_added } : undefined
    ,queuePosition: item.queue_position
    ,needsAttention: item.needs_attention
    ,auditSummary: item.audit_summary
  };
}

async function requestRun(path: string, init?: RequestInit): Promise<ResearchRunRecord> {
  const request = () => fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  let response: Response;
  try {
    response = await request();
  } catch (reason) {
    // A dev-server rebuild or a brief proxy interruption can drop an idempotent detail
    // request before an HTTP response exists. Retry reads once, but never replay writes.
    const method = (init?.method ?? "GET").toUpperCase();
    if (method !== "GET") throw new Error("研究服务连接中断，请稍后重试。", { cause: reason });
    await new Promise((resolve) => window.setTimeout(resolve, 250));
    try {
      response = await request();
    } catch (retryReason) {
      throw new Error("无法连接研究服务，请确认本地服务仍在运行后重试。", { cause: retryReason });
    }
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string | { message?: string } } | null;
    const detail = payload?.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || `研究接口返回 ${response.status}`);
  }
  return mapRun(await response.json() as ApiRun);
}

export const researchWorkflowGateway: ResearchWorkflowGateway = {
  async createRun(request) {
    const response = await fetch("/api/research-runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ topic: request.topic, theme: request.theme, objective: request.objective, output_type: "theme_report" }) });
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: string | { message?: string } } | null;
      const detail = payload?.detail;
      throw new Error(typeof detail === "string" ? detail : detail?.message || `研究接口返回 ${response.status}`);
    }
    const created = await response.json() as { run_id: string };
    return requestRun(`/api/research-runs/${encodeURIComponent(created.run_id)}`);
  },
  getRun(runId) { return requestRun(`/api/research-runs/${encodeURIComponent(runId)}`); },
  subscribeRun(runId, handlers) {
    let stopped = false;
    let source: EventSource | null = null;
    let pollTimer: number | undefined;
    let retryTimer: number | undefined;
    const pausedStates: ResearchRunState[] = ["waiting", "awaiting_theme_review", "awaiting_report_review", "completed", "returned", "cancelled", "failed", "blocked_configuration"];
    const clearPolling = () => { if (pollTimer !== undefined) window.clearInterval(pollTimer); pollTimer = undefined; };
    const stopTransport = () => { source?.close(); source = null; clearPolling(); if (retryTimer !== undefined) window.clearTimeout(retryTimer); retryTimer = undefined; };
    const deliver = (item: ApiRun) => {
      const mapped = mapRun(item);
      handlers.onSnapshot(mapped);
      if (pausedStates.includes(mapped.state)) { stopTransport(); handlers.onConnectionChange("closed"); }
    };
    const poll = async () => {
      try {
        const mapped = await requestRun(`/api/research-runs/${encodeURIComponent(runId)}`);
        handlers.onSnapshot(mapped);
        if (pausedStates.includes(mapped.state)) { stopTransport(); handlers.onConnectionChange("closed"); }
      } catch (reason) { handlers.onError(reason instanceof Error ? reason : new Error("研究状态读取失败")); }
    };
    const startPolling = () => {
      if (stopped || pollTimer !== undefined) return;
      handlers.onConnectionChange("polling");
      void poll();
      pollTimer = window.setInterval(poll, 2000);
    };
    const connect = () => {
      if (stopped) return;
      handlers.onConnectionChange("connecting");
      source?.close();
      source = new EventSource(`/api/research-runs/${encodeURIComponent(runId)}/stream`);
      source.onopen = () => { clearPolling(); handlers.onConnectionChange("live"); };
      source.addEventListener("run_snapshot", (event) => {
        try { deliver(JSON.parse((event as MessageEvent<string>).data) as ApiRun); }
        catch { handlers.onError(new Error("实时研究数据无法解析")); }
      });
      source.onerror = () => {
        if (stopped) return;
        source?.close(); source = null;
        handlers.onConnectionChange("reconnecting");
        startPolling();
        retryTimer = window.setTimeout(connect, 10000);
      };
    };
    connect();
    return () => { stopped = true; stopTransport(); };
  },
  async cancelRun(runId) {
    const response = await fetch(`/api/research-runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
    if (!response.ok) throw new Error(`研究接口返回 ${response.status}`);
    return requestRun(`/api/research-runs/${encodeURIComponent(runId)}`);
  },
  reviewTheme(runId, decision, note = "") { return requestRun(`/api/research-runs/${encodeURIComponent(runId)}/theme-review`, { method: "POST", body: JSON.stringify({ decision, note }) }); },
  reviewReport(runId, decision, note = "") { return requestRun(`/api/research-runs/${encodeURIComponent(runId)}/report-review`, { method: "POST", body: JSON.stringify({ decision, note }) }); },
  async rerun(runId) {
    const response = await fetch(`/api/research-runs/${encodeURIComponent(runId)}/rerun`, { method: "POST" });
    if (!response.ok) throw new Error(`研究接口返回 ${response.status}`);
    return requestRun(`/api/research-runs/${encodeURIComponent(runId)}`);
  },
  async finish(runId) {
    const response = await fetch(`/api/research-runs/${encodeURIComponent(runId)}/finish`, { method: "POST" });
    if (!response.ok) throw new Error(`结束任务接口返回 ${response.status}`);
  },
  async listRuns(limit = 50, offset = 0) {
    const response = await fetch(`/api/research-runs?limit=${limit}&offset=${offset}`, { headers: { Accept: "application/json" } });
    if (response.status === 405) throw new Error("当前运行的是旧版 API，请关闭旧服务并重新启动 ETF 主题雷达。");
    if (!response.ok) throw new Error(`任务列表接口返回 ${response.status}`);
    const payload = await response.json() as {
      runs: Array<{ run_id: string; topic: string; status: ResearchRunState; stage: string; progress: number; created_at: string; updated_at: string; queue_position?: number | null; needs_attention: boolean; output_type: ResearchRunListItem["outputType"] }>;
      total: number; has_more: boolean;
    };
    return {
      runs: payload.runs.map((run) => ({
        runId: run.run_id, topic: run.topic, state: run.status, stage: run.stage,
        progress: run.progress, createdAt: run.created_at, updatedAt: run.updated_at,
        queuePosition: run.queue_position, needsAttention: run.needs_attention, outputType: run.output_type,
      })),
      total: payload.total, hasMore: payload.has_more,
    };
  },
};
