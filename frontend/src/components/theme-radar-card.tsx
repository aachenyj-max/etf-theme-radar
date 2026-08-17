"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Clock3, FileSearch, Minus, ShieldAlert, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ThemeOpportunity, ThemeTrend } from "@/lib/theme-radar";
import { cn } from "@/lib/utils";

const MASONRY_ROW_HEIGHT = 8;
const MASONRY_VERTICAL_GAP = 16;
const MASONRY_MIN_CARD_HEIGHT = 470;
const INITIAL_MASONRY_ROW_SPAN = Math.ceil((MASONRY_MIN_CARD_HEIGHT + MASONRY_VERTICAL_GAP) / MASONRY_ROW_HEIGHT);

const masonryColumnClasses = {
  1: "lg:col-start-1",
  2: "lg:col-start-2",
  3: "lg:col-start-3"
} as const;

const trendMeta: Record<ThemeTrend, { label: string; Icon: typeof ArrowUpRight; className: string }> = {
  emerging: { label: "上升 · Emerging", Icon: ArrowUpRight, className: "text-signal" },
  stable: { label: "稳定 · Stable", Icon: ArrowRight, className: "text-ink/70" },
  cooling: { label: "降温 · Cooling", Icon: ArrowDownRight, className: "text-amber" },
  unknown: { label: "历史不足 · Unknown", Icon: Minus, className: "text-muted" }
};

const stageLabels = {
  emerging: "新兴信号",
  validating: "验证中",
  deep_research: "深度研究",
  monitoring: "持续观察"
};

function radarPoint(axis: number, value: number) {
  const angle = -Math.PI / 2 + axis * (Math.PI / 2);
  const radius = 34 * (value / 100);
  return `${50 + Math.cos(angle) * radius},${50 + Math.sin(angle) * radius}`;
}

function ThemeShape({ theme }: { theme: ThemeOpportunity }) {
  const values = [theme.metrics.themeScore, theme.metrics.researchMomentum, theme.metrics.commercialAdoption, theme.metrics.etfWhiteSpace];
  const points = values.map((value, axis) => radarPoint(axis, value)).join(" ");
  return (
    <svg viewBox="0 0 100 100" role="img" aria-label={`${theme.title}四项评分雷达图`} className="h-28 w-28">
      <polygon points="50,13 87,50 50,87 13,50" fill="none" stroke="#DDE3E3" strokeWidth="1" />
      <polygon points="50,25 75,50 50,75 25,50" fill="none" stroke="#E9ECEB" strokeWidth="1" />
      <path d="M50 10V90M10 50H90" stroke="#E6EAE9" strokeWidth="1" />
      <polygon points={points} fill="rgba(26,113,98,.14)" stroke="#1A7162" strokeWidth="2" strokeLinejoin="round" />
      {values.map((value, axis) => { const [x, y] = radarPoint(axis, value).split(","); return <circle key={axis} cx={x} cy={y} r="2.2" fill="#1A7162" />; })}
    </svg>
  );
}

function SignalDetail({ icon: Icon, label, text, tone }: { icon: typeof Sparkles; label: string; text: string; tone?: "risk" }) {
  return (
    <div className="flex gap-3 border-b border-line/80 pb-3 last:border-0 last:pb-0">
      <span className={cn("mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-signal/[0.08] text-signal", tone === "risk" && "bg-amber/[0.1] text-amber")}><Icon className="h-3.5 w-3.5" /></span>
      <div><p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">{label}</p><p className="mt-1 text-xs leading-5 text-ink/80">{text}</p></div>
    </div>
  );
}

export function ThemeRadarCard({ theme, coordinate, featured = false, masonryColumn = 1 }: { theme: ThemeOpportunity; coordinate: string; featured?: boolean; masonryColumn?: 1 | 2 | 3 }) {
  const [expanded, setExpanded] = useState(false);
  const [masonryRowSpan, setMasonryRowSpan] = useState(INITIAL_MASONRY_ROW_SPAN);
  const cardRef = useRef<HTMLElement>(null);
  const trend = trendMeta[theme.trend] ?? trendMeta.unknown;
  const TrendIcon = trend.Icon;
  const metrics = [
    ["研究动量", theme.metrics.researchMomentum],
    ["商业采用", theme.metrics.commercialAdoption],
    ["ETF 空白", theme.metrics.etfWhiteSpace]
  ] as const;

  useEffect(() => {
    const card = cardRef.current;
    if (!card) return;

    let animationFrame = 0;
    const updateRowSpan = () => {
      cancelAnimationFrame(animationFrame);
      animationFrame = requestAnimationFrame(() => {
        const cardHeight = card.getBoundingClientRect().height;
        const nextRowSpan = Math.max(1, Math.ceil((cardHeight + MASONRY_VERTICAL_GAP) / MASONRY_ROW_HEIGHT));
        setMasonryRowSpan((currentRowSpan) => currentRowSpan === nextRowSpan ? currentRowSpan : nextRowSpan);
      });
    };

    const resizeObserver = new ResizeObserver(updateRowSpan);
    resizeObserver.observe(card);
    updateRowSpan();

    return () => {
      cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
    };
  }, []);

  return (
    <article
      ref={cardRef}
      tabIndex={0}
      style={{ gridRowEnd: `span ${masonryRowSpan}` }}
      className={cn(
        "group relative min-h-[470px] self-start overflow-hidden rounded-2xl border border-line bg-paper p-5 shadow-card transition duration-300 focus-within:border-signal focus-within:outline-none hover:-translate-y-0.5 hover:border-ink/25 sm:p-6",
        featured ? "lg:col-span-2 lg:col-start-1" : masonryColumnClasses[masonryColumn]
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-muted/70">{coordinate}</span>
        <div className="flex items-center gap-2"><Badge className={theme.stage === "deep_research" ? "border-signal/20 bg-signal/[0.07] text-signal" : ""}>{stageLabels[theme.stage] ?? "待评估"}</Badge><span className={cn("flex items-center gap-1 text-[11px] font-semibold", trend.className)}><TrendIcon className="h-3.5 w-3.5" />{trend.label}</span></div>
      </div>

      <div className={cn("mt-6 grid items-center gap-4", featured ? "sm:grid-cols-[1fr_auto]" : "grid-cols-[1fr_auto]")}>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{theme.englishTitle}</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-ink">{theme.title}</h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-muted">{theme.description}</p>
        </div>
        <ThemeShape theme={theme} />
      </div>

      <div className="mt-6 flex items-end justify-between border-y border-line py-4">
        <div><p className="text-4xl font-semibold tracking-[-0.05em] text-ink">{theme.metrics.themeScore}</p><p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">Theme score</p></div>
        <div className="grid grid-cols-3 gap-5 text-right">{metrics.map(([label, value]) => <div key={label}><p className="text-lg font-semibold text-ink">{value}</p><p className="mt-1 text-[10px] text-muted">{label}</p></div>)}</div>
      </div>

      <div className="mt-5 flex items-center justify-between gap-4 text-xs text-muted">
        <div className="flex items-center gap-4"><span><strong className="font-semibold text-ink">{theme.metrics.companies}</strong> 家公司</span><span><strong className="font-semibold text-ink">{theme.evidenceCount}</strong> 条证据</span><span><strong className="font-semibold text-ink">{theme.sourceTypeCount}</strong> 类来源</span></div>
        <span className="flex items-center gap-1 whitespace-nowrap"><Clock3 className="h-3.5 w-3.5" />{theme.updatedAt}</span>
      </div>

      <Button variant="ghost" className="mt-4 w-full" asChild><Link href={`/theme-radar?theme=${encodeURIComponent(theme.slug)}`}>查看主题详情 <ArrowRight className="h-4 w-4" /></Link></Button>

      <button type="button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)} className="mt-5 flex w-full items-center justify-between rounded-xl border border-line bg-canvas/70 px-4 py-3 text-xs font-semibold text-ink transition hover:border-ink/20 lg:hidden">{expanded ? "收起关键信号" : "查看关键信号"}<Minus className="h-3.5 w-3.5" /></button>

      <div className="-mx-5 -mb-5 mt-5 border-t border-line bg-paper/98 sm:-mx-6 sm:-mb-6">
        <div className="hidden h-[46px] items-center justify-between px-5 lg:flex sm:px-6"><span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-signal">关键信号</span><span className="text-[10px] text-muted">悬停查看</span></div>
        <div className={cn("overflow-hidden opacity-0 transition-[max-height,opacity] duration-300 ease-out", expanded ? "max-h-[430px] opacity-100" : "max-h-0 lg:group-hover:max-h-[430px] lg:group-hover:opacity-100 lg:group-focus-within:max-h-[430px] lg:group-focus-within:opacity-100")}>
          <div className="space-y-3 border-t border-line/70 p-5 sm:p-6"><SignalDetail icon={Sparkles} label="最新催化剂" text={theme.latestCatalyst} /><SignalDetail icon={FileSearch} label="最新证据" text={theme.latestEvidence} /><SignalDetail icon={ShieldAlert} label="主要风险" text={theme.mainRisk} tone="risk" /><Button variant="outline" className="mt-5 w-full" asChild><Link href={`/research?theme=${theme.slug}`}>启动主题研究<ArrowRight className="h-4 w-4" /></Link></Button></div>
        </div>
      </div>
    </article>
  );
}
