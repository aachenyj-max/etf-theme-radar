"use client";

import { useEffect, useState } from "react";
import { ChevronDown, FilterX, LoaderCircle, Radar, RefreshCw, ShieldCheck } from "lucide-react";
import { ThemeRadarCard } from "@/components/theme-radar-card";
import { ThemeCandidateCard } from "@/components/theme-candidate-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ThemeRadarFilters, ThemeRadarLoadState, ThemeRadarSnapshot } from "@/lib/theme-radar";
import { themeRadarGateway } from "@/services/theme-radar-gateway";

const filterOptions = {
  sector: [
    ["all", "全部行业"], ["technology", "科技与算力"], ["industrials", "工业与制造"], ["energy", "能源"], ["semiconductors", "半导体"]
  ],
  source: [
    ["all", "全部来源"], ["sec", "SEC / 公司文件"], ["research", "论文与研究"], ["patents", "专利"], ["holdings", "ETF 持仓"], ["careers", "公司招聘"], ["market_discussion", "市场讨论"]
  ],
  period: [["30d", "最近 30 天"], ["90d", "最近 90 天"], ["1y", "最近 1 年"]],
  stage: [["all", "全部阶段"], ["emerging", "新兴信号"], ["validating", "验证中"], ["deep_research", "深度研究"], ["monitoring", "持续观察"]]
} as const;

const defaultFilters: ThemeRadarFilters = { sector: "all", source: "all", period: "90d", stage: "all" };

function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: ReadonlyArray<readonly [string, string]>; onChange: (value: string) => void }) {
  return (
    <label className="relative min-w-[160px] flex-1 lg:flex-none">
      <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.12em] text-muted/70">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 w-full appearance-none rounded-xl border border-line bg-paper pl-3 pr-9 text-sm font-medium text-ink outline-none transition hover:border-ink/20 focus:border-signal focus:ring-2 focus:ring-signal/10">
        {options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}
      </select>
      <ChevronDown className="pointer-events-none absolute bottom-3.5 right-3 h-4 w-4 text-muted" />
    </label>
  );
}

function LoadingMap() {
  return <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">{[0, 1, 2].map((item) => <div key={item} className="h-[470px] animate-pulse rounded-2xl border border-line bg-paper/70 first:lg:col-span-2" />)}</div>;
}

function getMasonryColumn(index: number): 1 | 2 | 3 {
  if (index === 0) return 1;
  return (((index + 1) % 3) + 1) as 1 | 2 | 3;
}

export function ThemeRadarWorkspace() {
  const [filters, setFilters] = useState<ThemeRadarFilters>(defaultFilters);
  const [loadState, setLoadState] = useState<ThemeRadarLoadState>("idle");
  const [snapshot, setSnapshot] = useState<ThemeRadarSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoadState(snapshot ? "refreshing" : "loading");
    setError(null);
    themeRadarGateway.listThemes(filters)
      .then((nextSnapshot) => { if (active) { setSnapshot(nextSnapshot); setLoadState(nextSnapshot.state); } })
      .catch((reason) => { if (active) { setError(reason instanceof Error ? reason.message : "主题雷达读取失败。" ); setLoadState("failed"); } });
    return () => { active = false; };
    // refreshKey 由手动刷新按钮驱动，代表后续 API 的重新拉取动作。
  }, [filters, refreshKey]);

  const emergingCount = snapshot?.themes.filter((theme) => theme.trend === "emerging").length ?? 0;
  const deepResearchCount = snapshot?.themes.filter((theme) => theme.stage === "deep_research").length ?? 0;

  function updateFilter<Key extends keyof ThemeRadarFilters>(key: Key, value: ThemeRadarFilters[Key]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function resetFilters() { setFilters(defaultFilters); }

  return (
    <div className="mx-auto max-w-[1500px] px-5 py-10 sm:px-8 sm:py-14 xl:px-12">
      <header className="border-b border-line pb-9">
        <div className="flex flex-wrap items-center gap-2"><Badge className="border-signal/20 bg-signal/[0.07] text-signal"><Radar className="mr-1 h-3 w-3" />Opportunity map</Badge><span className="text-xs text-muted">基于治理后的公开信息信号</span></div>
        <div className="mt-6 flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-4xl">
            <p className="text-sm font-semibold uppercase tracking-[0.14em] text-signal">Theme Radar</p>
            <h1 className="mt-3 text-[clamp(2.5rem,5vw,4.8rem)] font-semibold leading-[1.02] tracking-[-0.058em] text-ink">正在形成的投资主题</h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-muted">在主题变得拥挤之前，跟踪研究动量、商业采用和 ETF 产品空白。</p>
            <p className="mt-1 text-xs text-muted/70">Track emerging investment opportunities before they become crowded.</p>
          </div>
          <div className="flex items-center gap-6 border-l-2 border-signal pl-5 text-sm">
            <div><p className="text-2xl font-semibold tracking-[-0.04em] text-ink">{snapshot?.candidates.length ?? "—"}</p><p className="mt-1 text-xs text-muted">待验证信号</p></div>
            <div><p className="text-2xl font-semibold tracking-[-0.04em] text-signal">{emergingCount}</p><p className="mt-1 text-xs text-muted">信号上升</p></div>
            <div><p className="text-2xl font-semibold tracking-[-0.04em] text-ink">{deepResearchCount}</p><p className="mt-1 text-xs text-muted">深度研究</p></div>
          </div>
        </div>
      </header>

      <section className="sticky top-16 z-10 -mx-5 border-b border-line bg-canvas/95 px-5 py-5 backdrop-blur sm:-mx-8 sm:px-8 xl:-mx-12 xl:px-12" aria-label="主题筛选">
        <div className="mx-auto flex max-w-[1404px] flex-wrap items-end gap-3">
          <FilterSelect label="行业 Sector" value={filters.sector} options={filterOptions.sector} onChange={(value) => updateFilter("sector", value as ThemeRadarFilters["sector"])} />
          <FilterSelect label="数据来源 Data source" value={filters.source} options={filterOptions.source} onChange={(value) => updateFilter("source", value as ThemeRadarFilters["source"])} />
          <FilterSelect label="时间 Time period" value={filters.period} options={filterOptions.period} onChange={(value) => updateFilter("period", value as ThemeRadarFilters["period"])} />
          <FilterSelect label="阶段 Theme stage" value={filters.stage} options={filterOptions.stage} onChange={(value) => updateFilter("stage", value as ThemeRadarFilters["stage"])} />
          <Button variant="outline" size="icon" onClick={resetFilters} aria-label="重置筛选"><FilterX className="h-4 w-4" /></Button>
          <Button variant="ghost" size="icon" onClick={() => setRefreshKey((value) => value + 1)} aria-label="刷新主题雷达"><RefreshCw className={loadState === "refreshing" ? "h-4 w-4 animate-spin" : "h-4 w-4"} /></Button>
        </div>
      </section>

      <div className="mt-7 flex flex-col gap-3 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-4"><span className="flex items-center gap-1.5 text-signal">↗ 上升 Emerging</span><span className="text-ink/70">→ 稳定 Stable</span><span className="text-amber">↘ 降温 Cooling</span></div>
        <span className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5 text-signal" />{snapshot?.coverageNote ?? "正在读取主题覆盖"}</span>
      </div>

      {snapshot && snapshot.candidates.length > 0 && <section className="mt-6" aria-labelledby="candidate-signals-title">
        <div className="mb-4 flex items-end justify-between gap-4"><div><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber">Discovery queue</p><h2 id="candidate-signals-title" className="mt-1 text-2xl font-semibold tracking-[-0.04em] text-ink">待验证主题信号</h2></div><p className="max-w-lg text-right text-xs leading-5 text-muted">只展示跨证据聚类；通过可信度门槛后才参与排序，人工确认后才进入正式主题池。</p></div>
        <div className="space-y-4">{snapshot.candidates.filter((item) => !["confirmed", "merged", "rejected"].includes(item.status)).map((candidate) => <ThemeCandidateCard key={candidate.candidate_id} candidate={candidate} themes={snapshot.themes} onReviewed={() => setRefreshKey((value) => value + 1)} />)}</div>
      </section>}

      <section className="mt-5" aria-live="polite">
        {(loadState === "idle" || loadState === "loading") && <LoadingMap />}
        {loadState === "failed" && <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center"><p className="font-semibold text-red-800">主题雷达暂时无法读取</p><p className="mt-2 text-sm text-red-700">{error}</p><Button variant="outline" className="mt-5" onClick={() => setRefreshKey((value) => value + 1)}>重新加载</Button></div>}
        {loadState === "empty" && <div className="rounded-2xl border border-dashed border-ink/20 bg-paper px-6 py-16 text-center"><Radar className="mx-auto h-8 w-8 text-muted" /><h2 className="mt-4 text-xl font-semibold text-ink">没有符合条件的主题</h2><p className="mt-2 text-sm text-muted">放宽行业、来源或研究阶段条件，查看更多正在形成的信号。</p><Button variant="outline" className="mt-5" onClick={resetFilters}>清除全部筛选</Button></div>}
        {snapshot && (loadState === "ready" || loadState === "refreshing") && <div className={loadState === "refreshing" ? "relative grid auto-rows-[8px] grid-flow-row-dense grid-cols-1 items-start gap-x-4 opacity-60 transition lg:grid-cols-3" : "grid auto-rows-[8px] grid-flow-row-dense grid-cols-1 items-start gap-x-4 transition lg:grid-cols-3"}>{snapshot.themes.map((theme, index) => <ThemeRadarCard key={theme.id} theme={theme} coordinate={`TR-${String(index + 1).padStart(2, "0")}`} featured={index === 0} masonryColumn={getMasonryColumn(index)} />)}{loadState === "refreshing" && <div className="absolute inset-0 grid place-items-center rounded-2xl bg-canvas/20"><span className="flex items-center gap-2 rounded-full border border-line bg-paper px-4 py-2 text-xs font-semibold text-ink shadow-card"><LoaderCircle className="h-4 w-4 animate-spin text-signal" />正在刷新主题信号</span></div>}</div>}
      </section>
    </div>
  );
}
