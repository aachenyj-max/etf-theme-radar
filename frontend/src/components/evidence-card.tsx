"use client";

import { ArrowUpRight, CheckCircle2, Quote } from "lucide-react";
import type { EvidenceRecord } from "@/lib/evidence-explorer";
import { cn } from "@/lib/utils";

const sourceTone = {
  sec: "border-[#B9CBE0] bg-[#EFF5FA] text-[#315C82]",
  paper: "border-[#E6C8C8] bg-[#FBF1F1] text-[#8B3535]",
  patent: "border-[#D9D2EF] bg-[#F5F2FB] text-[#5B4C8B]",
  job: "border-[#C8DDD5] bg-[#EFF7F3] text-[#35705C]",
  company_update: "border-[#CAD9E6] bg-[#F0F5F8] text-[#315E7D]",
  social_discussion: "border-[#D7D9DB] bg-[#F3F4F4] text-[#45525C]"
} as const;

function SourceLogo({ item }: { item: EvidenceRecord }) {
  return (
    <span className="relative grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-xl border border-line bg-white">
      <span className="absolute text-[9px] font-bold uppercase tracking-tight text-muted">{item.sourceLabel.slice(0, 4)}</span>
      <img
        src={item.logoUrl}
        alt={`${item.publisher} Logo`}
        className="relative z-10 max-h-7 max-w-8 object-contain"
        onError={(event) => { event.currentTarget.style.display = "none"; }}
      />
    </span>
  );
}

export function EvidenceCard({ item, onSelect }: { item: EvidenceRecord; onSelect: (evidenceId: string) => void }) {
  const published = new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(item.publishedAt));

  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      className="group relative w-full rounded-2xl border border-line bg-paper p-5 text-left shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-ink/20 hover:shadow-[0_12px_36px_rgba(16,39,61,.07)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/30 sm:p-6"
    >
      <Quote className="absolute right-5 top-5 h-5 w-5 text-signal/15" />
      <div className="flex items-start gap-4 pr-7">
        <SourceLogo item={item} />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]", sourceTone[item.sourceType])}>{item.sourceLabel}</span>
            <span className="truncate text-xs text-muted">{item.publisher}</span>
          </div>
          <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.1em] text-muted/65">{published} · {item.id}</p>
        </div>
      </div>

      <h3 className="mt-5 text-[17px] font-semibold leading-7 tracking-[-0.015em] text-ink">{item.title}</h3>
      <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted">{item.summary}</p>

      <div className="mt-5 grid gap-3 border-t border-line pt-4 sm:grid-cols-[1fr_auto_auto] sm:items-center">
        <span className="flex items-center gap-2 text-xs font-medium text-ink">
          <CheckCircle2 className="h-4 w-4 text-signal" />
          {item.qualityLabel}
        </span>
        <span className="text-xs text-muted">来源质量 <strong className="font-semibold text-ink">{Math.round(item.sourceQuality * 100)}</strong></span>
        <span className="flex items-center justify-between gap-3 text-xs text-muted sm:justify-start">
          置信度 <strong className="font-semibold text-signal">{Math.round(item.confidence * 100)}%</strong>
          <ArrowUpRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </span>
      </div>
    </button>
  );
}

