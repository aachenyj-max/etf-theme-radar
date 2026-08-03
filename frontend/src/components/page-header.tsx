export function PageHeader({ index, eyebrow, title, description, actions }: { index: string; eyebrow: string; title: string; description: string; actions?: React.ReactNode }) {
  return (
    <header className="flex flex-col gap-6 border-b border-line pb-8 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-3xl">
        <p className="flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-signal"><span className="font-mono text-muted/70">{index}</span>{eyebrow}</p>
        <h1 className="mt-4 text-[clamp(2.25rem,5vw,4.2rem)] font-semibold leading-[1.03] tracking-[-0.055em] text-ink">{title}</h1>
        <p className="mt-5 max-w-2xl text-sm leading-6 text-muted sm:text-base sm:leading-7">{description}</p>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}
