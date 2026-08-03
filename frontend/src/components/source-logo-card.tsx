"use client";

import { useState } from "react";
import { CheckCircle2, Clock3, Settings2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type SourceState = "正常" | "降级" | "已关闭";

const stateMeta = {
  正常: { Icon: CheckCircle2, color: "text-signal", dot: "bg-signal" },
  降级: { Icon: Clock3, color: "text-amber", dot: "bg-amber" },
  已关闭: { Icon: Settings2, color: "text-muted", dot: "bg-muted" }
};

export function SourceLogoCard({ name, label, logo, state, freshness }: { name: string; label: string; logo?: string | null; state: SourceState; freshness: string }) {
  const [failed, setFailed] = useState(false);
  const { Icon, color, dot } = stateMeta[state];
  return (
    <article className="group relative min-w-[178px] rounded-2xl border border-line bg-paper p-4 transition duration-200 hover:-translate-y-0.5 hover:border-ink/20 hover:shadow-card">
      <div className="flex h-9 items-center justify-between gap-3">
        {failed || !logo ? (
          <span className="grid h-8 min-w-8 place-items-center rounded-lg bg-ink px-2 text-xs font-bold text-white">{name.slice(0, 3)}</span>
        ) : (
          // 外部品牌图用于演示；生产部署时应下载经许可的官方资产。
          // eslint-disable-next-line @next/next/no-img-element
          <img src={logo} alt={`${name} Logo`} className="max-h-8 max-w-[104px] object-contain object-left" onError={() => setFailed(true)} />
        )}
        <span className={cn("h-2 w-2 rounded-full", dot)} aria-label={state} />
      </div>
      <p className="mt-5 text-sm font-semibold text-ink">{label}</p>
      <div className={cn("mt-2 flex items-center gap-1.5 text-[11px]", color)}>
        <Icon className="h-3 w-3" aria-hidden="true" />
        <span>{state} · {freshness}</span>
      </div>
    </article>
  );
}
