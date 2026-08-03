export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="relative grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-ink text-white shadow-card" aria-hidden="true">
        <span className="h-4 w-4 rounded-full border-[3px] border-white" />
        <span className="absolute right-[8px] top-[8px] h-2 w-2 rounded-full bg-[#79B6A9] ring-2 ring-ink" />
      </div>
      {!compact && (
        <div>
          <p className="text-sm font-semibold tracking-[-0.01em] text-ink">ETF Theme Radar</p>
          <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted">Research Intelligence</p>
        </div>
      )}
    </div>
  );
}
