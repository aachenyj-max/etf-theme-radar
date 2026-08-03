"use client";

import { Archive, ArrowUpRight, FileText, Pencil, ShieldCheck, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ReportMutationAction, ResearchReportAsset } from "@/lib/report-library";
import { cn } from "@/lib/utils";

const statusMeta = {
  deep_research: { label: "深度研究", className: "border-signal/20 bg-signal/[0.07] text-signal" },
  watch: { label: "持续观察", className: "border-amber/20 bg-amber/[0.08] text-amber" },
  completed: { label: "已完成", className: "border-[#CAD9E6] bg-[#F0F5F8] text-[#315E7D]" },
  draft: { label: "草稿", className: "border-line bg-canvas text-muted" },
  archived: { label: "已归档", className: "border-line bg-ink/[0.04] text-muted" }
} as const;

const kindLabels = {
  theme_report: "主题研究",
  quick_scan: "快速扫描",
  etf_opportunity_analysis: "ETF 机会分析",
  event_report: "事件研究",
  landscape_scan: "格局扫描",
  evidence_brief: "证据简报"
} as const;

export function ReportCard({
  report,
  mutation,
  onOpen,
  onRename,
  onArchive,
  onDelete
}: {
  report: ResearchReportAsset;
  mutation?: ReportMutationAction;
  onOpen: (reportId: string) => void;
  onRename: (report: ResearchReportAsset) => void;
  onArchive: (report: ResearchReportAsset) => void;
  onDelete: (report: ResearchReportAsset) => void;
}) {
  const status = statusMeta[report.status];
  const updated = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" }).format(new Date(report.updatedAt));

  return (
    <article className={cn("group relative flex min-h-[330px] flex-col overflow-hidden rounded-2xl border border-line bg-paper p-5 shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-ink/20 hover:shadow-[0_14px_40px_rgba(16,39,61,.065)] sm:p-6", mutation && "pointer-events-none opacity-60")}>
      <div className="absolute right-0 top-0 h-16 w-16 bg-[linear-gradient(225deg,#F7F6F2_49%,#DDE3E3_50%,#FCFCFA_51%)] opacity-80" aria-hidden="true" />
      <div className="flex items-start justify-between gap-4 pr-10">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-line bg-canvas text-ink"><FileText className="h-5 w-5" /></div>
        <Badge className={status.className}>{status.label}</Badge>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.11em] text-muted">
        <span>{kindLabels[report.kind]}</span><span>·</span><span>V{report.version}</span>
        {report.auditPassed && <span className="flex items-center gap-1 text-signal"><ShieldCheck className="h-3 w-3" />审计通过</span>}
      </div>
      <h3 className="mt-3 text-lg font-semibold leading-7 tracking-[-0.025em] text-ink">{report.title}</h3>
      <p className="mt-2 text-xs text-muted">更新于 {updated}</p>
      <p className="mt-4 line-clamp-2 text-sm leading-6 text-muted">{report.summary}</p>

      <div className="mt-5 flex flex-wrap gap-1.5">
        {report.tags.map((tag) => <span key={tag} className="rounded-md border border-line bg-canvas px-2 py-1 text-[10px] font-medium text-muted">{tag}</span>)}
      </div>

      <div className="mt-auto pt-6">
        <div className="mb-4 flex items-center justify-between border-t border-line pt-4 text-[11px] text-muted"><span>{report.sourceCount} 类来源</span><span>{report.evidenceCount} 条证据</span></div>
        <div className="grid grid-cols-[1fr_auto_auto_auto] gap-2">
          <Button onClick={() => onOpen(report.id)}>打开<ArrowUpRight className="h-4 w-4" /></Button>
          <Button variant="outline" size="icon" onClick={() => onRename(report)} aria-label={`重命名 ${report.title}`} title="重命名"><Pencil className="h-4 w-4" /></Button>
          <Button variant="outline" size="icon" onClick={() => onArchive(report)} aria-label={`归档 ${report.title}`} title="归档" disabled={report.status === "archived"}><Archive className="h-4 w-4" /></Button>
          <Button variant="ghost" size="icon" onClick={() => onDelete(report)} aria-label={`删除 ${report.title}`} title="删除" className="hover:bg-red-50 hover:text-red-700"><Trash2 className="h-4 w-4" /></Button>
        </div>
      </div>

      {mutation && <span className="absolute inset-0 grid place-items-center bg-paper/50 text-xs font-semibold text-ink backdrop-blur-[1px]">{mutation === "renaming" ? "正在重命名" : mutation === "archiving" ? "正在归档" : "正在删除"}</span>}
    </article>
  );
}
