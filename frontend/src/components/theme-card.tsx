import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function ThemeCard({ title, status, score, evidence, change, sources, summary }: { title: string; status: string; score: number; evidence: number; change: string; sources: number; summary: string }) {
  return (
    <article className="rounded-2xl border border-line bg-paper p-5 shadow-card transition hover:border-ink/20">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Badge className={status === "重点研究" ? "border-signal/20 bg-signal/[0.07] text-signal" : ""}>{status}</Badge>
          <h3 className="mt-4 text-xl font-semibold tracking-[-0.025em] text-ink">{title}</h3>
        </div>
        <div className="text-right">
          <span className="text-3xl font-semibold tracking-[-0.04em] text-ink">{score}</span>
          <p className="text-[10px] uppercase tracking-[0.13em] text-muted">主题强度</p>
        </div>
      </div>
      <p className="mt-4 min-h-10 text-sm leading-6 text-muted">{summary}</p>
      <div className="mt-5 grid grid-cols-3 gap-3 border-y border-line py-3 text-center">
        <div><p className="text-sm font-semibold text-ink">{evidence}</p><p className="mt-0.5 text-[10px] text-muted">有效证据</p></div>
        <div><p className="text-sm font-semibold text-signal">{change}</p><p className="mt-0.5 text-[10px] text-muted">30 日变化</p></div>
        <div><p className="text-sm font-semibold text-ink">{sources}</p><p className="mt-0.5 text-[10px] text-muted">来源类型</p></div>
      </div>
      <Link href="/theme-radar" className="mt-4 flex items-center justify-between text-sm font-semibold text-ink hover:text-signal">
        查看主题证据 <ArrowUpRight className="h-4 w-4" />
      </Link>
    </article>
  );
}
