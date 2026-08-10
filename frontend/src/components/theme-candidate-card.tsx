"use client";

import { useState } from "react";
import { Check, GitMerge, ShieldQuestion, X } from "lucide-react";
import type { ThemeCandidate, ThemeOpportunity } from "@/lib/theme-radar";
import { Button } from "@/components/ui/button";

const statusLabel = { signal: "初始信号", validating: "交叉验证中", awaiting_confirmation: "等待确认", confirmed: "已确认", merged: "已合并", rejected: "已拒绝" };

function MiniBars({ items, labelKey }: { items: Array<Record<string, string | number>>; labelKey: string }) {
  const max = Math.max(1, ...items.map((item) => Number(item.count)));
  return <div className="space-y-2">{items.slice(-6).map((item) => <div key={String(item[labelKey])} className="grid grid-cols-[78px_1fr_24px] items-center gap-2 text-[11px]"><span className="truncate text-muted">{String(item[labelKey])}</span><span className="h-1.5 overflow-hidden rounded-full bg-line"><span className="block h-full rounded-full bg-signal" style={{ width: `${Number(item.count) / max * 100}%` }} /></span><span className="text-right font-medium text-ink">{item.count}</span></div>)}</div>;
}

export function ThemeCandidateCard({ candidate, themes, onReviewed }: { candidate: ThemeCandidate; themes: ThemeOpportunity[]; onReviewed: () => void }) {
  const [target, setTarget] = useState(themes[0]?.slug ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const blocks = candidate.metrics.visualization_blocks;
  const actionable = !["confirmed", "merged", "rejected"].includes(candidate.status);
  async function review(decision: "confirm" | "merge" | "reject") {
    setBusy(true); setError("");
    try {
      await import("@/services/theme-radar-gateway").then(({ themeRadarGateway }) => themeRadarGateway.reviewCandidate(candidate.candidate_id, decision, decision === "merge" ? target : ""));
      onReviewed();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "复核失败"); }
    finally { setBusy(false); }
  }
  return <article className="rounded-2xl border border-line bg-paper p-5 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-signal">Candidate signal</p><h3 className="mt-1 text-xl font-semibold tracking-[-0.03em] text-ink">{candidate.proposed_name}</h3><p className="mt-2 max-w-2xl text-sm leading-6 text-muted">{candidate.rationale}</p></div>
      <span className="rounded-full border border-amber/30 bg-amber/10 px-3 py-1 text-xs font-semibold text-amber">{statusLabel[candidate.status]}</span>
    </div>
    <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4">{[["证据", candidate.metrics.evidence_count], ["发布方", candidate.metrics.publisher_count], ["来源类型", candidate.metrics.source_type_count], ["实体", candidate.metrics.entity_count]].map(([label, value]) => <div key={label} className="bg-paper px-3 py-3"><p className="text-[10px] text-muted">{label}</p><p className="mt-1 text-lg font-semibold text-ink">{value}</p></div>)}</div>
    <div className="mt-5 grid gap-4 lg:grid-cols-4">
      <div className="rounded-xl border border-line p-3"><p className="mb-3 text-xs font-semibold text-ink">证据时间线</p><MiniBars items={blocks.evidence_timeline} labelKey="date" /></div>
      <div className="rounded-xl border border-line p-3"><p className="mb-3 text-xs font-semibold text-ink">来源扩散</p><MiniBars items={blocks.source_diffusion} labelKey="source_type" /></div>
      <div className="rounded-xl border border-line p-3"><p className="mb-3 text-xs font-semibold text-ink">实体覆盖</p><MiniBars items={blocks.entity_coverage} labelKey="label" /></div>
      <div className="rounded-xl border border-line p-3"><p className="text-xs font-semibold text-ink">ETF 覆盖 / 拥挤度</p><div className="mt-4 flex items-center gap-2"><ShieldQuestion className="h-5 w-5 text-amber" /><span className="text-sm font-semibold text-ink">{blocks.etf_coverage.status === "observed" ? `已观察 ${blocks.etf_coverage.evidence_count} 条` : "尚未评估"}</span></div><p className="mt-3 text-[11px] leading-5 text-muted">{blocks.etf_coverage.note}</p></div>
    </div>
    {actionable && <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-4">
      <Button size="sm" disabled={busy} onClick={() => review("confirm")}><Check className="mr-1.5 h-3.5 w-3.5" />确认主题</Button>
      <select aria-label="合并目标主题" value={target} onChange={(event) => setTarget(event.target.value)} className="h-9 rounded-lg border border-line bg-paper px-2 text-xs text-ink">{themes.map((theme) => <option key={theme.slug} value={theme.slug}>{theme.title}</option>)}</select>
      <Button size="sm" variant="outline" disabled={busy || !target} onClick={() => review("merge")}><GitMerge className="mr-1.5 h-3.5 w-3.5" />合并</Button>
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => review("reject")}><X className="mr-1.5 h-3.5 w-3.5" />拒绝</Button>
      {error && <span className="text-xs text-red-700">{error}</span>}
    </div>}
  </article>;
}
