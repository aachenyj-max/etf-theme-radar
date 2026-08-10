"use client";

import { useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowRight, CheckCircle2, Clock3, FilePlus2, History, Layers3,
  LoaderCircle, MessageSquareText, Radar, Search, Sparkles, X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ThemeCandidate, ThemeOpportunity, ThemeRadarSnapshot } from "@/lib/theme-radar";
import { themeRadarGateway } from "@/services/theme-radar-gateway";
import { cn } from "@/lib/utils";

const filters = { sector: "all", source: "all", period: "90d", stage: "all" } as const;

function CandidateResearchCard({ candidate, busy, onStart }: {
  candidate: ThemeCandidate; busy: boolean; onStart: (topic: string) => void;
}) {
  const metrics = candidate.metrics;
  return <article className="group relative overflow-hidden rounded-2xl border border-line bg-paper p-5 shadow-[0_1px_2px_rgba(16,39,61,.03)] transition hover:-translate-y-0.5 hover:border-ink/20 hover:shadow-card">
    <div className="absolute inset-y-0 left-0 w-1 bg-amber/65" />
    <div className="flex items-start justify-between gap-3">
      <div><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-amber">待确认主题</p><h3 className="mt-2 text-xl font-semibold tracking-[-.035em] text-ink">{candidate.proposed_name}</h3></div>
      <Badge className="border-amber/25 bg-amber/[.08] text-amber">{metrics.evidence_count} 条证据</Badge>
    </div>
    <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted">{candidate.rationale || candidate.description}</p>
    <div className="mt-5 grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-line bg-line text-center">
      {[["发布方", metrics.publisher_count], ["来源类型", metrics.source_type_count], ["实体", metrics.entity_count]].map(([label, value]) => <div key={label} className="bg-canvas px-2 py-3"><p className="text-base font-semibold text-ink">{value}</p><p className="mt-1 text-[10px] text-muted">{label}</p></div>)}
    </div>
    <Button className="mt-5 w-full" variant="outline" disabled={busy} onClick={() => onStart(candidate.proposed_name)}>确认边界并深入研究<ArrowRight className="h-4 w-4" /></Button>
  </article>;
}

function ConfirmedThemeDialog({ open, onOpenChange, themes, busy, onStart }: {
  open: boolean; onOpenChange: (open: boolean) => void; themes: ThemeOpportunity[]; busy: boolean;
  onStart: (topic: string, theme: string) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const key = query.trim().toLocaleLowerCase();
    return themes.filter((theme) => !key || `${theme.title} ${theme.englishTitle} ${theme.description}`.toLocaleLowerCase().includes(key));
  }, [query, themes]);
  return <Dialog.Root open={open} onOpenChange={onOpenChange}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-sm" />
      <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[calc(100%-2rem)] max-w-4xl -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl border border-line bg-paper shadow-2xl outline-none">
        <header className="border-b border-line px-6 py-5 sm:px-8">
          <div className="flex items-start justify-between gap-4"><div><Dialog.Title className="text-2xl font-semibold tracking-[-.04em] text-ink">继续研究已确认主题</Dialog.Title><Dialog.Description className="mt-2 text-sm leading-6 text-muted">选择主题后，系统会比较 30 天、90 天和 1 年产业动量，并在当前主报告版本链上生成待核实草稿。</Dialog.Description></div><Dialog.Close className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-line text-muted transition hover:text-ink" aria-label="关闭主题选择"><X className="h-4 w-4" /></Dialog.Close></div>
          <label className="mt-5 flex h-11 items-center gap-3 rounded-xl border border-line bg-canvas px-4 focus-within:border-signal"><Search className="h-4 w-4 text-muted" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索已确认主题" className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-muted/60" /></label>
        </header>
        <div className="max-h-[62vh] space-y-3 overflow-auto p-5 sm:p-6">
          {filtered.map((theme) => <button key={theme.slug} type="button" disabled={busy} onClick={() => onStart(theme.title, theme.slug)} className="group w-full rounded-2xl border border-line bg-paper p-5 text-left transition hover:border-signal/35 hover:bg-signal/[.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/25">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><h3 className="text-lg font-semibold tracking-[-.025em] text-ink">{theme.title}</h3><Badge>V{theme.reportVersion || 0}</Badge></div><p className="mt-2 max-w-2xl text-sm leading-6 text-muted">{theme.currentConclusion || "尚未发布正式主题结论。"}</p></div><ArrowRight className="mt-1 h-5 w-5 text-muted transition group-hover:translate-x-1 group-hover:text-signal" /></div>
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-line pt-4 text-[11px] text-muted"><span className="flex items-center gap-1.5"><Radar className="h-3.5 w-3.5" />动量：{theme.trend === "emerging" ? "上升" : theme.trend === "cooling" ? "降温" : theme.trend === "stable" ? "稳定" : "历史不足"}</span><span className="flex items-center gap-1.5"><Layers3 className="h-3.5 w-3.5" />{theme.evidenceCount} 条证据 · {theme.sourceTypeCount} 类来源</span><span className="flex items-center gap-1.5"><Clock3 className="h-3.5 w-3.5" />最近核实：{theme.lastVerifiedAt || "尚未发布"}</span></div>
          </button>)}
          {!filtered.length && <div className="rounded-2xl border border-dashed border-line p-8 text-center"><p className="text-sm font-semibold text-ink">没有匹配的已确认主题</p><p className="mt-2 text-xs text-muted">返回新主题入口提出研究主题，先完成边界确认。</p></div>}
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}

export function ResearchEntryPanel({ busy, queueBusy, onStart }: {
  busy: boolean; queueBusy: boolean; onStart: (topic: string, theme?: string) => Promise<void>;
}) {
  const [snapshot, setSnapshot] = useState<ThemeRadarSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmedOpen, setConfirmedOpen] = useState(false);
  const [proposal, setProposal] = useState("");

  useEffect(() => {
    let active = true;
    themeRadarGateway.listThemes(filters).then((value) => { if (active) { setSnapshot(value); setError(""); } }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "主题入口读取失败"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const candidates = (snapshot?.candidates ?? []).filter((item) => !["confirmed", "merged", "rejected"].includes(item.status));
  return <section className="overflow-hidden rounded-2xl border border-line bg-paper shadow-card">
    <header className="relative overflow-hidden border-b border-line bg-ink px-6 py-7 text-paper sm:px-8">
      <div className="absolute inset-y-0 right-0 w-40 opacity-20 [background:repeating-linear-gradient(135deg,transparent_0,transparent_12px,rgba(143,213,199,.35)_13px,transparent_14px)]" />
      <p className="text-[10px] font-semibold uppercase tracking-[.16em] text-[#8FD5C7]">Unified theme research</p>
      <h2 className="mt-3 max-w-3xl text-3xl font-semibold tracking-[-.045em]">分析 ETF 格局、跟踪产业动量</h2>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-paper/65">选择研究起点。来源和观察窗口由系统自动编排，最终只生成一份等待你核实的主题研究草稿。</p>
      <div className="mt-6 flex flex-wrap items-center gap-3 text-[11px] text-paper/65">{["主题边界", "产业与 ETF 研究", "证据审计", "核实发布"].map((item, index) => <span key={item} className="flex items-center gap-2"><span className={cn("grid h-6 w-6 place-items-center rounded-full border", index === 0 ? "border-[#8FD5C7] bg-[#8FD5C7]/15 text-[#8FD5C7]" : "border-paper/20")}>{index + 1}</span>{item}{index < 3 && <span className="ml-1 h-px w-5 bg-paper/20" />}</span>)}</div>
    </header>

    <div className="p-6 sm:p-8">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-signal/30 bg-signal/[.045] p-6"><div className="grid h-11 w-11 place-items-center rounded-xl bg-signal text-white"><Sparkles className="h-5 w-5" /></div><h3 className="mt-5 text-xl font-semibold text-ink">发现并确认新主题</h3><p className="mt-2 text-sm leading-6 text-muted">从跨来源候选卡片开始，或提出一个新主题。系统先确认定义和边界，再进入深入研究。</p><div className="mt-5 flex items-center gap-2 text-xs font-semibold text-signal"><CheckCircle2 className="h-4 w-4" />当前 {candidates.length} 个待确认信号</div></div>
        <button type="button" onClick={() => setConfirmedOpen(true)} className="group rounded-2xl border border-line bg-paper p-6 text-left transition hover:-translate-y-0.5 hover:border-ink/20 hover:shadow-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/25"><div className="grid h-11 w-11 place-items-center rounded-xl bg-ink/[.06] text-ink"><History className="h-5 w-5" /></div><div className="mt-5 flex items-center justify-between gap-3"><h3 className="text-xl font-semibold text-ink">继续研究已确认主题</h3><ArrowRight className="h-5 w-5 text-muted transition group-hover:translate-x-1 group-hover:text-signal" /></div><p className="mt-2 text-sm leading-6 text-muted">从现有结论和版本链继续讨论。只有新草稿核实通过后，才会发布下一版本。</p><div className="mt-5 flex items-center gap-2 text-xs font-semibold text-ink"><MessageSquareText className="h-4 w-4 text-signal" />当前 {snapshot?.themes.length ?? 0} 个已确认主题</div></button>
      </div>

      {error && <p role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</p>}
      <div className="mt-8 flex items-end justify-between gap-4 border-b border-line pb-4"><div><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-amber">New theme queue</p><h3 className="mt-1 text-xl font-semibold text-ink">选择一个新主题开始</h3></div><Badge>{queueBusy ? "将进入等待队列" : "可进入研究"}</Badge></div>
      {loading ? <div className="grid min-h-52 place-items-center"><LoaderCircle className="h-6 w-6 animate-spin text-signal" /></div> : <div className="mt-5 grid gap-4 xl:grid-cols-2">
        {candidates.map((candidate) => <CandidateResearchCard key={candidate.candidate_id} candidate={candidate} busy={busy} onStart={(topic) => void onStart(topic)} />)}
        <article className="rounded-2xl border border-dashed border-line bg-canvas/60 p-5"><div className="grid h-10 w-10 place-items-center rounded-xl bg-paper text-ink shadow-sm"><FilePlus2 className="h-5 w-5" /></div><h3 className="mt-4 text-lg font-semibold text-ink">提出一个新主题</h3><p className="mt-2 text-sm leading-6 text-muted">输入产业、技术或产品主题。下一步先核实主题定义，不会直接发布报告。</p><label className="mt-5 block"><span className="sr-only">新主题名称</span><input value={proposal} onChange={(event) => setProposal(event.target.value)} placeholder="例如：先进封装与 Chiplet" className="h-12 w-full rounded-xl border border-line bg-paper px-4 text-sm font-medium text-ink outline-none transition focus:border-signal focus:ring-2 focus:ring-signal/10" /></label><Button className="mt-3 w-full" disabled={busy || proposal.trim().length < 2} onClick={() => void onStart(proposal.trim())}>{busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}确认研究边界</Button></article>
      </div>}
    </div>
    <ConfirmedThemeDialog open={confirmedOpen} onOpenChange={setConfirmedOpen} themes={snapshot?.themes ?? []} busy={busy} onStart={(topic, theme) => void onStart(topic, theme)} />
  </section>;
}
