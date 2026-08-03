import { ArrowUpRight } from "lucide-react";

export function MetricCard({ label, value, detail, trend }: { label: string; value: string; detail: string; trend: string }) {
  return (
    <article className="rounded-2xl border border-line bg-paper p-5 shadow-card">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm font-medium text-muted">{label}</p>
        <ArrowUpRight className="h-4 w-4 text-muted/70" aria-hidden="true" />
      </div>
      <p className="mt-6 text-3xl font-semibold tracking-[-0.04em] text-ink">{value}</p>
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-line/80 pt-3 text-xs">
        <span className="text-muted">{detail}</span>
        <span className="whitespace-nowrap font-semibold text-signal">{trend}</span>
      </div>
    </article>
  );
}
