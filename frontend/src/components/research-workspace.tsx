"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import Link from "next/link";
import {
  Activity, AlertCircle, ArrowRight, BarChart3, Check, ChevronRight, CircleDot,
  FilePlus2, FileText, Landmark, ListChecks, LoaderCircle, NotebookPen, Radar,
  RotateCcw, ScanSearch, ShieldCheck, X
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  IntelligenceSourceId, ResearchDraft, ResearchObjective, ResearchOutputType,
  ResearchRunListItem, ResearchRunRecord, ResearchRunState, ResearchTimeRange,
  StreamConnectionState
} from "@/lib/research-workflow";
import { validateResearchDraft } from "@/lib/research-workflow";
import { cn } from "@/lib/utils";
import { researchWorkflowGateway } from "@/services/research-workflow-gateway";

const initialDraft: ResearchDraft = {
  topic: "", objective: "build_investment_thesis",
  sources: ["sec", "arxiv", "etf_holdings", "etf_news", "company_careers"],
  timeRange: "90d", outputType: "theme_report"
};
const objectives = [
  { id: "discover_emerging_themes" as const, title: "发现新兴主题", english: "Discover Emerging Themes", description: "从跨来源信号中识别尚未形成共识的投资叙事。", icon: Radar },
  { id: "analyze_etf_landscape" as const, title: "分析 ETF 格局", english: "Analyze ETF Landscape", description: "梳理现有产品、申报动态与主题覆盖缺口。", icon: Landmark },
  { id: "track_industry_momentum" as const, title: "跟踪产业动量", english: "Track Industry Momentum", description: "观察公司行动、招聘、论文与专利的变化速度。", icon: Activity },
  { id: "build_investment_thesis" as const, title: "构建投资假设", english: "Build Investment Thesis", description: "组织支持证据、反方证据与关键待验证事项。", icon: NotebookPen },
];
const intelligenceSources = [
  { id: "sec" as const, connector: "sec_edgar_etf", title: "SEC", description: "ETF 注册与公司文件", logo: "https://www.sec.gov/files/sec-logo.png" },
  { id: "arxiv" as const, connector: "openalex", title: "OpenAlex", description: "学术论文与研究活动", logo: "https://cdn.simpleicons.org/openaccess/10273D" },
  { id: "patents" as const, connector: "google_patents", title: "Patents", description: "Google Patents 公开发现", logo: "https://cdn.simpleicons.org/google/4285F4" },
  { id: "etf_holdings" as const, connector: "official_etf_holdings", title: "ETF Holdings", description: "发行人公开持仓与产品数据", logo: "https://www.google.com/s2/favicons?domain=ishares.com&sz=128" },
  { id: "etf_news" as const, connector: "yahoo_etf_news", title: "Yahoo Finance", description: "ETF 公开资讯与行情发现", logo: "https://cdn.simpleicons.org/yahoo/6001D2" },
  { id: "company_careers" as const, connector: "public_job_boards", title: "公司招聘", description: "公开职位与组织变化", logo: "https://cdn.simpleicons.org/greenhouse/357E63" },
  { id: "sp_global" as const, connector: "sp_global_dji", title: "S&P DJI", description: "指数公告与方法论", logo: "https://www.spglobal.com/spdji/en/images/application/global/sp-dow-jones-indices-marketing.png" },
  { id: "x" as const, connector: "anysearch_discovery", title: "X", description: "专家与市场讨论", logo: "https://cdn.simpleicons.org/x/10273D" },
  { id: "forums" as const, connector: "anysearch_discovery", title: "Forums", description: "公开论坛与观点线索", logo: "https://www.google.com/s2/favicons?domain=seekingalpha.com&sz=128" },
];
const timeRanges: Array<{ id: ResearchTimeRange; label: string }> = [
  { id: "30d", label: "近 30 天" }, { id: "90d", label: "近 90 天" },
  { id: "1y", label: "近 1 年" }, { id: "custom", label: "自定义" },
];
const outputTypes = [
  { id: "quick_scan" as const, title: "快速扫描", english: "Quick Scan", description: "快速整理信号、来源覆盖和优先缺口。", meta: "约 1–2 分钟", icon: ScanSearch },
  { id: "theme_report" as const, title: "主题研究", english: "Theme Research", description: "形成支持证据、反方检查和可审计研究结论。", meta: "约 3–6 分钟", icon: FileText },
  { id: "etf_opportunity_analysis" as const, title: "ETF 机会分析", english: "ETF Opportunity", description: "在主题研究基础上核验竞品、持仓覆盖与产品缺口。", meta: "快速档 2–4 分钟", icon: BarChart3 },
];
const runningStates = new Set<ResearchRunState>([
  "planning", "queued", "collecting", "governing", "analyzing", "auditing",
]);
const attentionStates = new Set<ResearchRunState>([
  "awaiting_theme_review", "awaiting_report_review", "returned", "blocked_configuration",
]);
const statusLabel: Record<string, string> = {
  waiting: "等待中", planning: "规划研究边界", awaiting_theme_review: "需要主题复核",
  queued: "等待 Worker", collecting: "采集公开来源", governing: "治理与去重",
  analyzing: "形成证据结论", auditing: "事实审计", awaiting_report_review: "需要报告复核",
  returned: "已退回，待处理", completed: "已完成", cancelled: "已结束",
  blocked_configuration: "配置阻断", failed: "运行失败",
};

function SectionHeading({ step, title, english, description }: { step: string; title: string; english: string; description?: string }) {
  return <div className="mb-4 flex items-start gap-3"><span className="mt-0.5 font-mono text-[10px] font-semibold text-signal">{step}</span><div><h3 className="text-base font-semibold text-ink">{title}</h3><p className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.11em] text-muted/65">{english}</p>{description && <p className="mt-2 text-xs leading-5 text-muted">{description}</p>}</div></div>;
}

function ChoiceCard({ selected, disabled = false, onClick, className, children }: {
  selected: boolean; disabled?: boolean; onClick: () => void; className?: string; children: React.ReactNode;
}) {
  return <button type="button" aria-pressed={selected} disabled={disabled} onClick={onClick} className={cn(
    "group relative overflow-hidden rounded-2xl border bg-paper p-5 text-left shadow-[0_1px_2px_rgba(16,39,61,.03)] transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/30",
    selected ? "border-signal/45 bg-signal/[0.055] shadow-[0_8px_24px_rgba(43,138,120,.08)]" : "border-line hover:-translate-y-0.5 hover:border-ink/20 hover:shadow-card",
    disabled && "cursor-not-allowed opacity-50 hover:translate-y-0 hover:border-line hover:shadow-none",
    className,
  )}>{selected && <span className="absolute right-3 top-3 grid h-5 w-5 place-items-center rounded-full bg-signal text-white"><Check className="h-3 w-3" /></span>}{children}</button>;
}

function LedgerItem({ item, selected, onSelect }: { item: ResearchRunListItem; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button" onClick={onSelect} aria-current={selected ? "page" : undefined}
      className={cn(
        "group relative w-full border-l-2 px-4 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal",
        selected ? "border-signal bg-signal/[0.07]" : "border-line hover:border-ink/30 hover:bg-ink/[0.025]"
      )}
    >
      <span className={cn("absolute -left-[5px] top-5 h-2 w-2 rounded-full border-2 bg-canvas", selected ? "border-signal" : "border-line")} />
      <span className="block truncate text-sm font-semibold text-ink">{item.topic}</span>
      <span className="mt-1 flex items-center justify-between gap-2 text-[10px] text-muted">
        <span>{statusLabel[item.state] ?? item.stage}</span>
        <span>{item.state === "waiting" ? `第 ${item.queuePosition ?? 1} 位` : `${item.progress}%`}</span>
      </span>
    </button>
  );
}

function LedgerSection({ title, items, selectedId, onSelect, empty }: {
  title: string; items: ResearchRunListItem[]; selectedId?: string;
  onSelect: (id: string) => void; empty: string;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between px-3">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{title}</h2>
        <span className="font-mono text-[10px] text-muted">{items.length}</span>
      </div>
      {items.length ? items.map((item) => (
        <LedgerItem key={item.runId} item={item} selected={selectedId === item.runId} onSelect={() => onSelect(item.runId)} />
      )) : <p className="px-4 py-3 text-[11px] text-muted/75">{empty}</p>}
    </section>
  );
}

function RunDetail({ run, connection, onReview, onCancel, onRerun, onFinish }: {
  run: ResearchRunRecord; connection: StreamConnectionState;
  onReview: (gate: "theme" | "report", decision: "approve" | "return") => void;
  onCancel: () => void; onRerun: () => void; onFinish: () => void;
}) {
  const definition = run.result?.theme_definition;
  const summary = run.auditSummary;
  const terminal = ["completed", "cancelled", "failed", "blocked_configuration"].includes(run.state);
  return (
    <article className="rounded-2xl border border-line bg-paper shadow-card">
      <header className="border-b border-line p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Badge className={run.needsAttention ? "border-amber/25 bg-amber/[0.08] text-amber" : "border-signal/20 bg-signal/[0.07] text-signal"}>
              {statusLabel[run.state] ?? run.stageLabel}
            </Badge>
            {run.state === "waiting" && <Badge>队列第 {run.queuePosition ?? 1} 位</Badge>}
          </div>
          <span className="flex items-center gap-2 text-[10px] text-muted">
            <CircleDot className={cn("h-3 w-3", connection === "live" ? "animate-pulse text-signal" : "text-muted")} />
            {connection === "live" ? "实时更新" : connection === "polling" ? "轮询更新" : "持久化快照"}
          </span>
        </div>
        <h1 className="mt-5 text-3xl font-semibold tracking-[-0.045em] text-ink">{run.request.topic}</h1>
        <p className="mt-2 font-mono text-[10px] text-muted">{run.runId}</p>
        <div className="mt-7 h-1.5 overflow-hidden rounded-full bg-ink/[0.07]">
          <div className="h-full bg-signal transition-all" style={{ width: `${run.progress}%` }} />
        </div>
        <div className="mt-2 flex justify-between text-xs"><span className="text-muted">{run.stageLabel}</span><strong>{run.progress}%</strong></div>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl bg-canvas p-3"><p className="text-[10px] text-muted">授权来源</p><p className="mt-1 text-sm font-semibold">{run.request.sources.length} 个</p></div>
          <div className="rounded-xl bg-canvas p-3"><p className="text-[10px] text-muted">原始入库增量</p><p className="mt-1 text-sm font-semibold">+{run.evidenceProgress?.rawAdded ?? 0}</p></div>
          <div className="rounded-xl bg-canvas p-3"><p className="text-[10px] text-muted">主题有效增量</p><p className="mt-1 text-sm font-semibold text-signal">+{run.evidenceProgress?.relevantAdded ?? 0}</p></div>
        </div>
      </header>

      <div className="p-6 sm:p-8">
        {run.state === "waiting" && <div className="rounded-xl border border-dashed border-line p-5 text-sm leading-6 text-muted">当前活动任务结束、取消、失败或配置阻断后，本任务会原子提升并开始规划。切换页面不会影响队列。</div>}
        {run.state === "awaiting_theme_review" && definition && (
          <div className="rounded-xl border border-signal/20 bg-signal/[0.05] p-5">
            <h2 className="font-semibold text-ink">{definition.name}</h2>
            <p className="mt-2 text-sm leading-6 text-muted">{definition.description}</p>
            <div className="mt-5 flex gap-2"><Button onClick={() => onReview("theme", "approve")}>通过并继续</Button><Button variant="outline" onClick={() => onReview("theme", "return")}>退回</Button></div>
          </div>
        )}
        {run.state === "awaiting_report_review" && (
          <div className="rounded-xl border border-signal/20 bg-signal/[0.05] p-5">
            <h2 className="font-semibold text-ink">报告已生成，等待你的复核</h2>
            <p className="mt-2 text-sm text-muted">通过后进入报告库；退回任务仍占用活动槽，直到重跑或结束。</p>
            <div className="mt-5 flex gap-2"><Button onClick={() => onReview("report", "approve")}>通过报告</Button><Button variant="outline" onClick={() => onReview("report", "return")}>退回</Button></div>
          </div>
        )}
        {run.error && <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{run.error}</p>}

        <details className="mt-6 rounded-xl border border-line bg-canvas">
          <summary className="cursor-pointer list-none px-5 py-4 text-sm font-semibold text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal">
            <span className="flex items-center justify-between"><span className="flex items-center gap-2"><ListChecks className="h-4 w-4 text-signal" />执行详情</span><span className="text-xs font-normal text-muted">决策摘要与工具工作流</span></span>
          </summary>
          <div className="grid gap-6 border-t border-line p-5 lg:grid-cols-2">
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">决策摘要</h3>
              <dl className="mt-4 space-y-3 text-xs">
                <div><dt className="text-muted">研究目标</dt><dd className="mt-1 text-ink">{summary?.researchObjective ?? run.request.objective}</dd></div>
                <div><dt className="text-muted">反方检查</dt><dd className="mt-1 text-ink">{summary?.counterCheck ? "已执行" : "尚未记录"}</dd></div>
                <div><dt className="text-muted">停止原因</dt><dd className="mt-1 text-ink">{summary?.stopReason || "工作流仍在推进"}</dd></div>
                <div><dt className="text-muted">剩余缺口</dt><dd className="mt-1 text-ink">{summary?.remainingGaps?.join("；") || "尚无结构化缺口"}</dd></div>
              </dl>
            </section>
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">工具与工作流</h3>
              <p className="mt-4 text-xs text-muted">模型请求 {summary?.usage.modelRequests ?? 0} 次 · 工具调用 {summary?.usage.toolCalls ?? run.toolCalls?.length ?? 0} 次</p>
              <ol className="mt-3 max-h-56 space-y-2 overflow-auto">
                {(run.toolCalls ?? []).map((call) => <li key={call.id} className="flex justify-between gap-3 rounded-lg bg-paper px-3 py-2 text-[11px]"><span>{call.name}</span><span className="text-muted">{call.status} · +{call.relevantEvidenceDelta ?? 0}</span></li>)}
                {!run.toolCalls?.length && <li className="text-xs text-muted">尚无工具记录。</li>}
              </ol>
            </section>
          </div>
        </details>

        <div className="mt-6 flex flex-wrap gap-2">
          {run.state === "completed" && <Button asChild><Link href="/reports">进入报告库<ArrowRight className="h-4 w-4" /></Link></Button>}
          {run.state === "returned" && <><Button variant="outline" onClick={onRerun}><RotateCcw className="h-4 w-4" />按当前定义重新运行</Button><Button variant="ghost" onClick={onFinish}>结束任务并释放队列</Button></>}
          {!terminal && !run.state.startsWith("awaiting_") && run.state !== "returned" && <Button variant="outline" onClick={onCancel}><X className="h-4 w-4" />停止任务</Button>}
        </div>
      </div>
    </article>
  );
}

export function ResearchWorkspace() {
  const gateway = researchWorkflowGateway;
  const [draft, setDraft] = useState<ResearchDraft>(initialDraft);
  const [errors, setErrors] = useState<ReturnType<typeof validateResearchDraft>>({});
  const [runs, setRuns] = useState<ResearchRunListItem[]>([]);
  const [selectedRun, setSelectedRun] = useState<ResearchRunRecord | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [connection, setConnection] = useState<StreamConnectionState>("closed");
  const [streamEpoch, setStreamEpoch] = useState(0);
  const [returnGate, setReturnGate] = useState<"theme" | "report" | null>(null);
  const [returnNote, setReturnNote] = useState("");
  const [listError, setListError] = useState("");
  const [selectionError, setSelectionError] = useState("");
  const [outputCapabilities, setOutputCapabilities] = useState<Record<ResearchOutputType, boolean>>({ quick_scan: false, theme_report: true, etf_opportunity_analysis: false });
  const [connectorCapabilities, setConnectorCapabilities] = useState<Record<string, { enabled: boolean; status: string; coverage_note: string; logo_url?: string | null }>>({});

  const loadRuns = useCallback(async () => {
    try {
      const payload = await gateway.listRuns();
      setRuns(payload.runs); setListError("");
    } catch (reason) {
      setListError(reason instanceof Error ? reason.message : "任务账本读取失败");
    }
  }, [gateway]);
  const selectRun = useCallback(async (runId: string) => {
    try {
      const run = await gateway.getRun(runId);
      setSelectedRun(run);
      setSelectionError("");
      window.history.replaceState(null, "", `?run=${encodeURIComponent(runId)}`);
    } catch (reason) {
      setSelectionError(reason instanceof Error ? reason.message : "任务详情读取失败，请重试。");
    }
  }, [gateway]);

  useEffect(() => {
    void loadRuns().then(async () => {
      const runId = new URLSearchParams(window.location.search).get("run");
      if (runId) await selectRun(runId);
    });
  }, [loadRuns, selectRun]);
  useEffect(() => {
    let active = true;
    void fetch("/api/capabilities", { headers: { Accept: "application/json" } })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(String(response.status))))
      .then((payload: { output_types?: Partial<Record<ResearchOutputType, boolean>>; connectors?: Array<{ source_name: string; enabled: boolean; status: string; coverage_note: string; logo_url?: string | null }> }) => {
        if (!active) return;
        setOutputCapabilities((current) => ({ ...current, ...payload.output_types }));
        setConnectorCapabilities(Object.fromEntries((payload.connectors ?? []).map((item) => [item.source_name, item])));
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!selectedRun || ["waiting", "completed", "failed", "cancelled", "blocked_configuration", "returned"].includes(selectedRun.state)) {
      setConnection("closed"); return;
    }
    return gateway.subscribeRun(selectedRun.runId, {
      onSnapshot: (run) => { setSelectedRun(run); void loadRuns(); },
      onConnectionChange: setConnection,
      onError: (error) => setSelectedRun((current) => current ? { ...current, error: error.message } : current),
    });
  }, [gateway, selectedRun?.runId, streamEpoch, loadRuns]);

  const grouped = useMemo(() => ({
    attention: runs.filter((run) => attentionStates.has(run.state)),
    running: runs.filter((run) => runningStates.has(run.state)),
    waiting: runs.filter((run) => run.state === "waiting"),
    history: runs.filter((run) => !attentionStates.has(run.state) && !runningStates.has(run.state) && run.state !== "waiting"),
  }), [runs]);
  const capacityFull = grouped.waiting.length > 0 && (grouped.running.length > 0 || grouped.attention.length > 0);
  const selectedSources = useMemo(() => new Set(draft.sources), [draft.sources]);

  function toggleSource(source: IntelligenceSourceId) {
    setDraft((current) => ({ ...current, sources: current.sources.includes(source) ? current.sources.filter((item) => item !== source) : [...current.sources, source] }));
    setErrors((current) => ({ ...current, sources: undefined }));
  }

  async function startResearch(event: React.FormEvent) {
    event.preventDefault();
    const nextErrors = validateResearchDraft(draft); setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setSubmitting(true);
    try {
      const created = await gateway.createRun({ ...draft, topic: draft.topic.trim() });
      setSelectedRun(created); window.history.replaceState(null, "", `?run=${encodeURIComponent(created.runId)}`);
      await loadRuns(); setStreamEpoch((value) => value + 1);
    } catch (reason) {
      setErrors({ topic: reason instanceof Error ? reason.message : "任务创建失败" });
    } finally { setSubmitting(false); }
  }
  async function review(gate: "theme" | "report", decision: "approve" | "return") {
    if (!selectedRun) return;
    if (decision === "return") { setReturnGate(gate); return; }
    setSelectedRun(gate === "theme" ? await gateway.reviewTheme(selectedRun.runId, decision) : await gateway.reviewReport(selectedRun.runId, decision));
    await loadRuns(); setStreamEpoch((value) => value + 1);
  }
  async function confirmReturn() {
    if (!selectedRun || !returnGate || !returnNote.trim()) return;
    setSelectedRun(returnGate === "theme" ? await gateway.reviewTheme(selectedRun.runId, "return", returnNote.trim()) : await gateway.reviewReport(selectedRun.runId, "return", returnNote.trim()));
    setReturnGate(null); setReturnNote(""); await loadRuns();
  }

  return (
    <div className="mx-auto max-w-[1500px] px-4 py-7 sm:px-7 xl:px-10">
      <header className="mb-7 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-6">
        <div><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-signal">Research ledger</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.045em] text-ink">研究任务管理</h1><p className="mt-2 text-sm text-muted">单执行槽 · 最多保留一个等待任务</p></div>
        <Button variant="outline" onClick={() => { setSelectedRun(null); window.history.replaceState(null, "", "/research"); }}><FilePlus2 className="h-4 w-4" />新建任务</Button>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[290px_minmax(0,1fr)]">
        <aside className="overflow-hidden rounded-2xl border border-line bg-paper shadow-card lg:sticky lg:top-20">
          <div className="border-b border-line bg-ink px-5 py-4 text-paper"><p className="text-sm font-semibold">任务账本</p><p className="mt-1 text-[10px] text-paper/55">{runs.length} 条持久化记录</p></div>
          <div className="max-h-[calc(100vh-220px)] space-y-5 overflow-auto py-4">
            {listError && <p className="mx-3 rounded-lg bg-red-50 p-3 text-xs text-red-700">{listError}</p>}
            <LedgerSection title="需要处理" items={grouped.attention} selectedId={selectedRun?.runId} onSelect={(id) => void selectRun(id)} empty="没有待复核任务" />
            <LedgerSection title="正在运行" items={grouped.running} selectedId={selectedRun?.runId} onSelect={(id) => void selectRun(id)} empty="执行槽当前空闲" />
            <LedgerSection title="等待中" items={grouped.waiting} selectedId={selectedRun?.runId} onSelect={(id) => void selectRun(id)} empty="等待槽当前空闲" />
            <LedgerSection title="历史任务" items={grouped.history} selectedId={selectedRun?.runId} onSelect={(id) => void selectRun(id)} empty="还没有历史记录" />
          </div>
        </aside>

        <main className="min-w-0">
          {selectionError && <div role="alert" className="mb-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /><p>{selectionError}</p></div>}
          {selectedRun ? (
            <RunDetail
              run={selectedRun} connection={connection} onReview={review}
              onCancel={async () => { await gateway.cancelRun(selectedRun.runId); await selectRun(selectedRun.runId); await loadRuns(); }}
              onRerun={async () => { setSelectedRun(await gateway.rerun(selectedRun.runId)); await loadRuns(); setStreamEpoch((value) => value + 1); }}
              onFinish={async () => { await gateway.finish(selectedRun.runId); setSelectedRun(null); window.history.replaceState(null, "", "/research"); await loadRuns(); }}
            />
          ) : (
            <form onSubmit={startResearch} className="rounded-2xl border border-line bg-paper p-6 shadow-card sm:p-8">
              <div className="flex items-start justify-between gap-4"><div><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-signal">New mandate</p><h2 className="mt-2 text-2xl font-semibold tracking-[-0.035em] text-ink">新建研究任务</h2></div><Badge>{capacityFull ? "容量已满" : grouped.running.length || grouped.attention.length ? "将进入等待" : "可立即运行"}</Badge></div>
              {capacityFull && <div className="mt-5 flex gap-3 rounded-xl border border-amber/25 bg-amber/[0.07] p-4 text-sm leading-6 text-ink"><AlertCircle className="mt-1 h-4 w-4 shrink-0 text-amber" /><p>当前已有一个活动任务和一个等待任务。第三个任务不能创建；完成、取消活动任务，或取消等待任务后即可释放容量。</p></div>}
              <div className="mt-8 space-y-10">
                <section>
                  <SectionHeading step="01" title="研究主题" english="Research topic" description="用一句明确的产业、技术或产品主题定义本次研究。" />
                  <div className={cn("rounded-2xl border bg-canvas p-2 transition focus-within:border-signal focus-within:ring-2 focus-within:ring-signal/10", errors.topic ? "border-red-300" : "border-line")}>
                    <input aria-label="研究主题" value={draft.topic} onChange={(event) => { setDraft((value) => ({ ...value, topic: event.target.value })); setErrors((current) => ({ ...current, topic: undefined })); }} placeholder="例如：AI 基础设施" className="h-14 w-full rounded-xl bg-transparent px-4 text-xl font-semibold tracking-[-0.02em] text-ink outline-none placeholder:font-normal placeholder:text-muted/50" />
                  </div>
                  {errors.topic && <p className="mt-2 text-xs font-medium text-red-700">{errors.topic}</p>}
                </section>

                <section>
                  <SectionHeading step="02" title="研究目标" english="Research objective" description="选择本次任务最重要的一个结果。" />
                  <div className="grid gap-3 md:grid-cols-2">{objectives.map(({ id, title, english, description, icon: Icon }) => <ChoiceCard key={id} selected={draft.objective === id} onClick={() => setDraft((current) => ({ ...current, objective: id }))} className="min-h-[190px]"><div className={cn("grid h-10 w-10 place-items-center rounded-xl transition", draft.objective === id ? "bg-signal text-white" : "bg-ink/[0.055] text-ink")}><Icon className="h-5 w-5" /></div><h4 className="mt-5 pr-8 text-base font-semibold text-ink">{title}</h4><p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted/70">{english}</p><p className="mt-3 text-sm leading-6 text-muted">{description}</p></ChoiceCard>)}</div>
                </section>

                <section>
                  <SectionHeading step="03" title="选择情报来源" english="Select intelligence sources" description="组合可审计来源；关闭或降级的连接器不能选入任务。" />
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">{intelligenceSources.map(({ id, connector, title, description, logo }) => { const selected = selectedSources.has(id); const capability = connectorCapabilities[connector]; const unavailable = Boolean(capability && (!capability.enabled || capability.status !== "healthy")); const resolvedLogo = capability?.logo_url ?? logo; return <ChoiceCard key={id} selected={selected} disabled={unavailable} onClick={() => toggleSource(id)} className="min-h-[164px] p-4"><div className="flex h-9 items-center">{resolvedLogo ? <img src={resolvedLogo} alt={`${title} Logo`} className="max-h-8 max-w-[94px] object-contain object-left" /> : <span className="grid h-8 min-w-8 place-items-center rounded-lg bg-ink px-2 text-xs font-bold text-white">{title.slice(0, 3)}</span>}</div><h4 className="mt-5 pr-5 text-sm font-semibold text-ink">{title}</h4><p className="mt-1 text-[11px] leading-4 text-muted">{description}</p>{capability && <p className={cn("mt-2 text-[10px] font-semibold", unavailable ? "text-amber" : "text-signal")}>{unavailable ? "当前不可用" : "连接正常"}</p>}</ChoiceCard>; })}</div>
                  {errors.sources && <p className="mt-2 text-xs font-medium text-red-700">{errors.sources}</p>}
                </section>

                <section>
                  <SectionHeading step="04" title="观察区间" english="Time range" />
                  <div className="inline-flex w-full flex-wrap gap-1 rounded-2xl border border-line bg-[#EFEEE9] p-1.5 sm:w-auto">{timeRanges.map(({ id, label }) => <button key={id} type="button" aria-pressed={draft.timeRange === id} onClick={() => setDraft((current) => ({ ...current, timeRange: id, customDateRange: id === "custom" ? current.customDateRange ?? { from: "", to: "" } : undefined }))} className={cn("min-w-[92px] flex-1 rounded-xl px-5 py-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/30 sm:flex-none", draft.timeRange === id ? "bg-white text-ink shadow-[0_1px_4px_rgba(16,39,61,.08)]" : "text-muted hover:text-ink")}>{label}</button>)}</div>
                  {draft.timeRange === "custom" && <div className="mt-4 grid max-w-xl gap-3 sm:grid-cols-2"><label className="text-xs font-medium text-muted">开始日期<input type="date" value={draft.customDateRange?.from ?? ""} onChange={(event) => setDraft((current) => ({ ...current, customDateRange: { from: event.target.value, to: current.customDateRange?.to ?? "" } }))} className="mt-2 h-11 w-full rounded-xl border border-line bg-canvas px-3 text-sm text-ink outline-none focus:border-signal" /></label><label className="text-xs font-medium text-muted">结束日期<input type="date" value={draft.customDateRange?.to ?? ""} onChange={(event) => setDraft((current) => ({ ...current, customDateRange: { from: current.customDateRange?.from ?? "", to: event.target.value } }))} className="mt-2 h-11 w-full rounded-xl border border-line bg-canvas px-3 text-sm text-ink outline-none focus:border-signal" /></label></div>}
                  {errors.customDateRange && <p className="mt-2 text-xs font-medium text-red-700">{errors.customDateRange}</p>}
                </section>

                <section>
                  <SectionHeading step="05" title="输出类型" english="Output type" description="输出越深入，需要的交叉核验与审计时间越长。" />
                  <div className="grid gap-3 md:grid-cols-3">{outputTypes.map(({ id, title, english, description, meta, icon: Icon }) => { const available = outputCapabilities[id]; return <ChoiceCard key={id} selected={draft.outputType === id} disabled={!available} onClick={() => setDraft((current) => ({ ...current, outputType: id }))} className="min-h-[226px]"><div className={cn("grid h-10 w-10 place-items-center rounded-xl transition", draft.outputType === id ? "bg-signal text-white" : "bg-ink/[0.055] text-ink")}><Icon className="h-5 w-5" /></div><h4 className="mt-5 pr-7 text-base font-semibold text-ink">{title}</h4><p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted/70">{english}</p><p className="mt-3 text-sm leading-6 text-muted">{description}</p><p className="mt-4 text-xs font-semibold text-signal">{available ? meta : "后端能力未就绪"}</p></ChoiceCard>; })}</div>
                </section>
              </div>
              <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6"><p className="flex max-w-xl gap-2 text-xs leading-5 text-muted"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-signal" />模型仅处理受控证据与结构化摘要；界面不展示或保存隐藏思维链。</p><Button type="submit" disabled={submitting || capacityFull}>{submitting ? <><LoaderCircle className="h-4 w-4 animate-spin" />正在创建</> : <>开始研究<ChevronRight className="h-4 w-4" /></>}</Button></div>
            </form>
          )}
        </main>
      </div>

      <Dialog.Root open={returnGate !== null} onOpenChange={(open) => { if (!open) { setReturnGate(null); setReturnNote(""); } }}>
        <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-ink/25 backdrop-blur-sm" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-paper p-6 shadow-2xl outline-none"><Dialog.Title className="text-lg font-semibold text-ink">退回{returnGate === "theme" ? "主题定义" : "研究报告"}</Dialog.Title><Dialog.Description className="mt-2 text-sm leading-6 text-muted">复核备注会进入持久审计记录，任务不会自动重跑。</Dialog.Description><label className="mt-5 block text-xs font-semibold text-ink">复核备注<textarea aria-label="复核备注" autoFocus value={returnNote} onChange={(event) => setReturnNote(event.target.value)} rows={5} className="mt-2 w-full resize-none rounded-xl border border-line bg-canvas p-3 text-sm outline-none focus:border-signal" /></label><div className="mt-6 flex justify-end gap-2"><Dialog.Close asChild><Button variant="ghost">取消</Button></Dialog.Close><Button disabled={!returnNote.trim()} onClick={() => void confirmReturn()}>确认退回</Button></div></Dialog.Content></Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
