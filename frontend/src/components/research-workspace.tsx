"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import Link from "next/link";
import { Activity, AlertCircle, ArrowRight, CircleDot, FilePlus2, ListChecks, LoaderCircle, RotateCcw, X } from "lucide-react";
import { ResearchEntryPanel } from "@/components/research-entry-panel";
import { ConversationResearchWorkspace } from "@/components/conversation-research-workspace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ResearchDraft, ResearchRunListItem, ResearchRunRecord, ResearchRunState, StreamConnectionState } from "@/lib/research-workflow";
import { validateResearchDraft } from "@/lib/research-workflow";
import { cn } from "@/lib/utils";
import { researchWorkflowGateway } from "@/services/research-workflow-gateway";

const initialDraft: ResearchDraft = {
  topic: "",
  objective: "analyze_etf_landscape_and_track_industry_momentum",
  sources: [],
  timeRange: "multi_horizon",
  outputType: "theme_report",
};

const runningStates = new Set<ResearchRunState>(["planning", "queued", "collecting", "governing", "analyzing", "auditing"]);
const attentionStates = new Set<ResearchRunState>(["awaiting_theme_review", "awaiting_report_review", "returned", "blocked_configuration"]);
const statusLabel: Record<string, string> = {
  waiting: "等待中", planning: "规划研究边界", awaiting_theme_review: "需要主题复核",
  queued: "等待 Worker", collecting: "采集公开来源", governing: "治理与去重",
  analyzing: "形成证据结论", auditing: "事实审计", awaiting_report_review: "需要报告复核",
  returned: "已退回，待处理", completed: "已完成", cancelled: "已结束",
  blocked_configuration: "配置阻断", failed: "运行失败",
};

function LedgerItem({ item, selected, onSelect }: { item: ResearchRunListItem; selected: boolean; onSelect: () => void }) {
  return <button type="button" onClick={onSelect} aria-current={selected ? "page" : undefined} className={cn(
    "group relative w-full border-l-2 px-4 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal",
    selected ? "border-signal bg-signal/[0.07]" : "border-line hover:border-ink/30 hover:bg-ink/[0.025]",
  )}>
    <span className={cn("absolute -left-[5px] top-5 h-2 w-2 rounded-full border-2 bg-canvas", selected ? "border-signal" : "border-line")} />
    <span className="block truncate text-sm font-semibold text-ink">{item.topic}</span>
    <span className="mt-1 flex items-center justify-between gap-2 text-[10px] text-muted"><span>{statusLabel[item.state] ?? item.stage}</span><span>{item.state === "waiting" ? `第 ${item.queuePosition ?? 1} 位` : `${item.progress}%`}</span></span>
  </button>;
}

function LedgerSection({ title, items, selectedId, onSelect, empty }: { title: string; items: ResearchRunListItem[]; selectedId?: string; onSelect: (id: string) => void; empty: string }) {
  return <section>
    <div className="mb-2 flex items-center justify-between px-3"><h2 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{title}</h2><span className="font-mono text-[10px] text-muted">{items.length}</span></div>
    {items.length ? items.map((item) => <LedgerItem key={item.runId} item={item} selected={selectedId === item.runId} onSelect={() => onSelect(item.runId)} />) : <p className="px-4 py-3 text-[11px] text-muted/75">{empty}</p>}
  </section>;
}

function RunDetail({ run, connection, reviewPending, onReview, onCancel, onRerun, onFinish }: {
  run: ResearchRunRecord; connection: StreamConnectionState; reviewPending: boolean;
  onReview: (gate: "theme" | "report", decision: "approve" | "return") => void;
  onCancel: () => void; onRerun: () => void; onFinish: () => void;
}) {
  const definition = run.result?.theme_definition;
  const summary = run.auditSummary;
  const conclusion = run.result?.conclusion;
  const gaps = conclusion?.evidence_gaps ?? run.result?.report_sections?.evidence_gaps ?? [];
  const terminal = ["completed", "cancelled", "failed", "blocked_configuration"].includes(run.state);
  const liveCalls = (run.toolCalls ?? []).slice(-6).reverse();
  return <article className="rounded-2xl border border-line bg-paper shadow-card">
    <header className="border-b border-line p-6 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3"><Badge className={run.needsAttention ? "border-amber/25 bg-amber/[0.08] text-amber" : "border-signal/20 bg-signal/[0.07] text-signal"}>{statusLabel[run.state] ?? run.stageLabel}</Badge><span className="flex items-center gap-2 text-[10px] text-muted"><CircleDot className={cn("h-3 w-3", connection === "live" ? "animate-pulse text-signal" : "text-muted")} />{connection === "live" ? "实时更新" : connection === "polling" ? "轮询更新" : "持久化快照"}</span></div>
      <h1 className="mt-5 text-3xl font-semibold tracking-[-0.045em] text-ink">{run.request.topic}</h1>
      <p className="mt-2 font-mono text-[10px] text-muted">{run.runId}</p>
      <div className="mt-7 h-1.5 overflow-hidden rounded-full bg-ink/[0.07]"><div className="h-full bg-signal transition-all" style={{ width: `${run.progress}%` }} /></div>
      <div className="mt-2 flex justify-between text-xs"><span className="text-muted">{run.stageLabel}</span><strong>{run.progress}%</strong></div>
      <div className="mt-6 grid gap-3 sm:grid-cols-3"><div className="rounded-xl bg-canvas p-3"><p className="text-[10px] text-muted">来源调度</p><p className="mt-1 text-sm font-semibold">系统自动选择</p></div><div className="rounded-xl bg-canvas p-3"><p className="text-[10px] text-muted">原始入库增量</p><p className="mt-1 text-sm font-semibold">+{run.evidenceProgress?.rawAdded ?? 0}</p></div><div className="rounded-xl bg-canvas p-3"><p className="text-[10px] text-muted">主题有效增量</p><p className="mt-1 text-sm font-semibold text-signal">+{run.evidenceProgress?.relevantAdded ?? 0}</p></div></div>
    </header>
    <div className="p-6 sm:p-8">
      {run.state === "waiting" && <div className="rounded-xl border border-dashed border-line p-5 text-sm leading-6 text-muted">任务已进入 FIFO 等待队列。切换页面不会影响执行，活动任务释放执行槽后会自动提升。</div>}
      {run.state === "awaiting_theme_review" && definition && <div className="rounded-xl border border-signal/20 bg-signal/[0.05] p-5"><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-signal">主题边界确认</p><h2 className="mt-2 font-semibold text-ink">{definition.name}</h2><p className="mt-2 text-sm leading-6 text-muted">{definition.description}</p><div className="mt-5 flex gap-2"><Button disabled={reviewPending} onClick={() => onReview("theme", "approve")}>{reviewPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}确认并深入研究</Button><Button variant="outline" disabled={reviewPending} onClick={() => onReview("theme", "return")}>调整主题边界</Button></div></div>}
      {run.state === "awaiting_report_review" && <div className="rounded-xl border border-signal/20 bg-signal/[0.05] p-5">
        <p className="text-[10px] font-semibold uppercase tracking-[.14em] text-signal">待核实研究草稿</p><h2 className="mt-2 text-lg font-semibold text-ink">{conclusion?.statement || "报告已生成，等待你的复核。"}</h2>
        <p className="mt-2 text-sm leading-6 text-muted">只有你确认后才会追加到该主题的规范版本链；放弃本轮更新不会改变现有报告。</p>
        {gaps.length > 0 && <div className="mt-4 rounded-xl border border-amber/20 bg-paper p-4"><p className="text-xs font-semibold text-amber">仍需关注的证据缺口</p><ul className="mt-3 space-y-2 text-xs leading-5 text-muted">{gaps.slice(0, 3).map((gap, index) => <li key={`${gap.area}-${index}`}><strong className="text-ink">{gap.area}：</strong>{gap.gap}<span className="block pl-0 text-muted/80">影响：{gap.impact}</span></li>)}</ul></div>}
        <div className="mt-5 flex flex-wrap gap-2"><Button disabled={reviewPending} onClick={() => onReview("report", "approve")}>{reviewPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}确认并发布</Button><Button variant="outline" disabled={reviewPending} onClick={() => onReview("report", "return")}>要求补充研究</Button><Button variant="ghost" disabled={reviewPending} onClick={onCancel}>放弃本轮更新</Button></div>
      </div>}
      {run.error && <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{run.error}</p>}
      {!terminal && run.state !== "waiting" && !run.state.startsWith("awaiting_") && run.state !== "returned" && <section className="mt-6 rounded-xl border border-signal/20 bg-signal/[0.035] p-5" aria-live="polite"><div className="flex items-center justify-between gap-3"><h2 className="flex items-center gap-2 text-sm font-semibold text-ink"><Activity className="h-4 w-4 text-signal" />实时研究流</h2><span className="text-[10px] text-muted">仅展示事实采集与审计事件</span></div><ol className="mt-4 space-y-2">{liveCalls.map((call) => <li key={call.id} className="flex items-center justify-between gap-3 rounded-lg bg-paper px-3 py-2 text-xs"><span className="min-w-0 truncate text-ink">{call.currentSource ? `${call.currentSource} · ` : ""}{call.name}</span><span className="shrink-0 text-muted">{call.status}{call.relevantEvidenceDelta ? ` · 主题证据 +${call.relevantEvidenceDelta}` : ""}</span></li>)}{!liveCalls.length && <li className="text-xs text-muted">任务已进入执行流程，等待第一条采集事件。</li>}</ol></section>}
      <details className="mt-6 rounded-xl border border-line bg-canvas"><summary className="cursor-pointer list-none px-5 py-4 text-sm font-semibold text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal"><span className="flex items-center justify-between"><span className="flex items-center gap-2"><ListChecks className="h-4 w-4 text-signal" />执行详情</span><span className="text-xs font-normal text-muted">决策摘要与工具工作流</span></span></summary><div className="grid gap-6 border-t border-line p-5 lg:grid-cols-2"><section><h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">决策摘要</h3><dl className="mt-4 space-y-3 text-xs"><div><dt className="text-muted">研究目标</dt><dd className="mt-1 text-ink">分析 ETF 格局、跟踪产业动量</dd></div><div><dt className="text-muted">反方检查</dt><dd className="mt-1 text-ink">{summary?.counterCheck ? "已执行" : "尚未记录"}</dd></div><div><dt className="text-muted">停止原因</dt><dd className="mt-1 text-ink">{summary?.stopReason || "工作流仍在推进"}</dd></div><div><dt className="text-muted">剩余缺口</dt><dd className="mt-1 text-ink">{summary?.remainingGaps?.join("；") || "尚无结构化缺口"}</dd></div></dl></section><section><h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">工具与工作流</h3><p className="mt-4 text-xs text-muted">模型请求 {summary?.usage.modelRequests ?? 0} 次 · 工具调用 {summary?.usage.toolCalls ?? run.toolCalls?.length ?? 0} 次</p><ol className="mt-3 max-h-56 space-y-2 overflow-auto">{(run.toolCalls ?? []).map((call) => <li key={call.id} className="flex justify-between gap-3 rounded-lg bg-paper px-3 py-2 text-[11px]"><span>{call.name}</span><span className="text-muted">{call.status} · +{call.relevantEvidenceDelta ?? 0}</span></li>)}</ol></section></div></details>
      <div className="mt-6 flex flex-wrap gap-2">{run.state === "completed" && <Button asChild><Link href="/reports">进入报告库<ArrowRight className="h-4 w-4" /></Link></Button>}{run.state === "returned" && <><Button variant="outline" onClick={onRerun}><RotateCcw className="h-4 w-4" />按当前定义重新运行</Button><Button variant="ghost" onClick={onFinish}>结束任务</Button></>}{!terminal && !run.state.startsWith("awaiting_") && run.state !== "returned" && <Button variant="outline" onClick={onCancel}><X className="h-4 w-4" />停止任务</Button>}</div>
    </div>
  </article>;
}

export function LegacyResearchWorkspace() {
  const gateway = researchWorkflowGateway;
  const [runs, setRuns] = useState<ResearchRunListItem[]>([]);
  const [selectedRun, setSelectedRun] = useState<ResearchRunRecord | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [reviewPending, setReviewPending] = useState(false);
  const [connection, setConnection] = useState<StreamConnectionState>("closed");
  const [streamEpoch, setStreamEpoch] = useState(0);
  const [returnGate, setReturnGate] = useState<"theme" | "report" | null>(null);
  const [returnNote, setReturnNote] = useState("");
  const [listError, setListError] = useState("");
  const [selectionError, setSelectionError] = useState("");

  const loadRuns = useCallback(async () => { try { const payload = await gateway.listRuns(); setRuns(payload.runs); setListError(""); } catch (reason) { setListError(reason instanceof Error ? reason.message : "任务账本读取失败"); } }, [gateway]);
  const selectRun = useCallback(async (runId: string) => { try { const run = await gateway.getRun(runId); setSelectedRun(run); setSelectionError(""); window.history.replaceState(null, "", `?run=${encodeURIComponent(runId)}`); } catch (reason) { setSelectionError(reason instanceof Error ? reason.message : "任务详情读取失败，请重试。"); } }, [gateway]);

  useEffect(() => { void loadRuns().then(async () => { const runId = new URLSearchParams(window.location.search).get("run"); if (runId) await selectRun(runId); }); }, [loadRuns, selectRun]);
  useEffect(() => {
    if (!selectedRun || ["waiting", "completed", "failed", "cancelled", "blocked_configuration", "returned"].includes(selectedRun.state)) { setConnection("closed"); return; }
    return gateway.subscribeRun(selectedRun.runId, { onSnapshot: (run) => { setSelectedRun(run); void loadRuns(); }, onConnectionChange: setConnection, onError: (error) => setSelectedRun((current) => current ? { ...current, error: error.message } : current) });
  }, [gateway, selectedRun?.runId, streamEpoch, loadRuns]);

  const grouped = useMemo(() => ({ attention: runs.filter((run) => attentionStates.has(run.state)), running: runs.filter((run) => runningStates.has(run.state)), waiting: runs.filter((run) => run.state === "waiting"), history: runs.filter((run) => !attentionStates.has(run.state) && !runningStates.has(run.state) && run.state !== "waiting") }), [runs]);

  async function startResearch(topic: string, theme?: string) {
    const request = { ...initialDraft, topic: topic.trim(), theme };
    const error = validateResearchDraft(request).topic;
    if (error) { setSelectionError(error); return; }
    setSubmitting(true); setSelectionError("");
    try { const created = await gateway.createRun(request); setSelectedRun(created); window.history.replaceState(null, "", `?run=${encodeURIComponent(created.runId)}`); await loadRuns(); setStreamEpoch((value) => value + 1); } catch (reason) { setSelectionError(reason instanceof Error ? reason.message : "任务创建失败"); } finally { setSubmitting(false); }
  }
  async function review(gate: "theme" | "report", decision: "approve" | "return") {
    if (!selectedRun || reviewPending) return;
    if (decision === "return") { setReturnGate(gate); return; }
    setReviewPending(true); setSelectionError("");
    try { const updated = gate === "theme" ? await gateway.reviewTheme(selectedRun.runId, decision) : await gateway.reviewReport(selectedRun.runId, decision); setSelectedRun(updated); await loadRuns(); setStreamEpoch((value) => value + 1); } catch (reason) { setSelectionError(reason instanceof Error ? reason.message : "复核提交失败，请按最新任务状态重试。"); try { setSelectedRun(await gateway.getRun(selectedRun.runId)); } catch {} } finally { setReviewPending(false); }
  }
  async function confirmReturn() {
    if (!selectedRun || !returnGate || !returnNote.trim() || reviewPending) return;
    setReviewPending(true); setSelectionError("");
    try {
      const returned = returnGate === "theme" ? await gateway.reviewTheme(selectedRun.runId, "return", returnNote.trim()) : await gateway.reviewReport(selectedRun.runId, "return", returnNote.trim());
      const updated = returnGate === "report" ? await gateway.rerun(returned.runId) : returned;
      setSelectedRun(updated); setReturnGate(null); setReturnNote(""); await loadRuns(); if (returnGate === "report") setStreamEpoch((value) => value + 1);
    } catch (reason) { setSelectionError(reason instanceof Error ? reason.message : "退回复核失败，请按最新任务状态重试。"); setReturnGate(null); setReturnNote(""); try { setSelectedRun(await gateway.getRun(selectedRun.runId)); } catch {} } finally { setReviewPending(false); }
  }

  return <div className="mx-auto max-w-[1500px] px-4 py-7 sm:px-7 xl:px-10">
    <header className="mb-7 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-6"><div><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-signal">Theme research desk</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.045em] text-ink">主题研究工作台</h1><p className="mt-2 text-sm text-muted">分析 ETF 格局、跟踪产业动量 · 单一规范报告版本链</p></div><Button variant="outline" onClick={() => { setSelectedRun(null); window.history.replaceState(null, "", "/research"); }}><FilePlus2 className="h-4 w-4" />开始主题研究</Button></header>
    <div className="grid items-start gap-6 lg:grid-cols-[290px_minmax(0,1fr)]"><aside className="order-2 overflow-hidden rounded-2xl border border-line bg-paper shadow-card lg:order-1 lg:sticky lg:top-20"><div className="border-b border-line bg-ink px-5 py-4 text-paper"><p className="text-sm font-semibold">任务账本</p><p className="mt-1 text-[10px] text-paper/55">{runs.length} 条持久化记录</p></div><div className="max-h-[calc(100vh-220px)] space-y-5 overflow-auto py-4">{listError && <p className="mx-3 rounded-lg bg-red-50 p-3 text-xs text-red-700">{listError}</p>}<LedgerSection title="正在运行" items={grouped.running} selectedId={selectedRun?.runId} onSelect={(id) => void selectRun(id)} empty="执行槽当前空闲" /><LedgerSection title="等待中" items={grouped.waiting} selectedId={selectedRun?.runId} onSelect={(id) => void selectRun(id)} empty="等待队列当前为空" /><LedgerSection title="需要处理" items={grouped.attention} selectedId={selectedRun?.runId} onSelect={(id) => void selectRun(id)} empty="没有待复核任务" /><LedgerSection title="历史任务" items={grouped.history} selectedId={selectedRun?.runId} onSelect={(id) => void selectRun(id)} empty="还没有历史记录" /></div></aside>
      <main className="order-1 min-w-0 lg:order-2">{selectionError && <div role="alert" className="mb-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /><p>{selectionError}</p></div>}{selectedRun ? <RunDetail run={selectedRun} connection={connection} reviewPending={reviewPending} onReview={review} onCancel={async () => { try { await gateway.cancelRun(selectedRun.runId); await selectRun(selectedRun.runId); await loadRuns(); } catch (reason) { setSelectionError(reason instanceof Error ? reason.message : "操作失败"); } }} onRerun={async () => { try { setSelectedRun(await gateway.rerun(selectedRun.runId)); await loadRuns(); setStreamEpoch((value) => value + 1); } catch (reason) { setSelectionError(reason instanceof Error ? reason.message : "重新运行失败"); } }} onFinish={async () => { try { await gateway.finish(selectedRun.runId); setSelectedRun(null); window.history.replaceState(null, "", "/research"); await loadRuns(); } catch (reason) { setSelectionError(reason instanceof Error ? reason.message : "结束任务失败"); } }} /> : <ResearchEntryPanel busy={submitting} queueBusy={Boolean(grouped.running.length || grouped.waiting.length)} onStart={startResearch} />}</main>
    </div>
    <Dialog.Root open={returnGate !== null} onOpenChange={(open) => { if (!open) { setReturnGate(null); setReturnNote(""); } }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-ink/25 backdrop-blur-sm" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-paper p-6 shadow-2xl outline-none"><Dialog.Title className="text-lg font-semibold text-ink">{returnGate === "report" ? "要求补充研究" : "调整主题边界"}</Dialog.Title><Dialog.Description className="mt-2 text-sm leading-6 text-muted">{returnGate === "report" ? "请具体说明缺少哪方面的证据、为何会影响判断。备注会写入审计记录，任务随后重新进入等待队列。" : "请说明主题定义或研究边界需要如何调整。备注会写入持久化审计记录。"}</Dialog.Description><label className="mt-5 block text-xs font-semibold text-ink">{returnGate === "report" ? "需要补充什么" : "需要调整什么"}<textarea aria-label="复核备注" autoFocus value={returnNote} onChange={(event) => setReturnNote(event.target.value)} rows={5} className="mt-2 w-full resize-none rounded-xl border border-line bg-canvas p-3 text-sm outline-none focus:border-signal" /></label><div className="mt-6 flex justify-end gap-2"><Dialog.Close asChild><Button variant="ghost">取消</Button></Dialog.Close><Button disabled={!returnNote.trim() || reviewPending} onClick={() => void confirmReturn()}>{reviewPending && <LoaderCircle className="h-4 w-4 animate-spin" />}{returnGate === "report" ? "提交并重新排队" : "提交调整"}</Button></div></Dialog.Content></Dialog.Portal></Dialog.Root>
  </div>;
}

export function ResearchWorkspace() {
  return <ConversationResearchWorkspace fallback={<LegacyResearchWorkspace />} />;
}
