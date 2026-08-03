import { cn } from "@/lib/utils";

export function Badge({ children, className }: React.PropsWithChildren<{ className?: string }>) {
  return <span className={cn("inline-flex items-center rounded-full border border-line px-2.5 py-1 text-[11px] font-semibold tracking-wide text-muted", className)}>{children}</span>;
}
