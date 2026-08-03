import type { LucideIcon } from "lucide-react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";

export function EmptyState({ icon: Icon, eyebrow, title, description, action }: { icon: LucideIcon; eyebrow: string; title: string; description: string; action: string }) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-dashed border-ink/20 bg-paper px-6 py-16 text-center shadow-card sm:px-12">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-signal/40 to-transparent" />
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-line bg-canvas text-ink"><Icon className="h-5 w-5" /></div>
      <p className="mt-5 text-[11px] font-semibold uppercase tracking-[0.16em] text-signal">{eyebrow}</p>
      <h2 className="mx-auto mt-3 max-w-lg text-2xl font-semibold tracking-[-0.03em] text-ink">{title}</h2>
      <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-muted">{description}</p>
      <Button className="mt-7">{action}<ArrowRight className="h-4 w-4" /></Button>
    </section>
  );
}
