import { Badge } from "@/components/ui/badge";

export function ResearchTaskCard({ title, theme, stage, progress, owner, updated }: { title: string; theme: string; stage: string; progress: number; owner: string; updated: string }) {
  return (
    <article className="rounded-2xl border border-line bg-paper p-5 shadow-card">
      <div className="flex items-center justify-between gap-3"><Badge>{theme}</Badge><span className="text-xs text-muted">{updated}</span></div>
      <h3 className="mt-4 font-semibold text-ink">{title}</h3>
      <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-ink/[0.07]"><div className="h-full rounded-full bg-signal" style={{ width: `${progress}%` }} /></div>
      <div className="mt-3 flex items-center justify-between text-xs text-muted"><span>{stage} · {progress}%</span><span>{owner}</span></div>
    </article>
  );
}
