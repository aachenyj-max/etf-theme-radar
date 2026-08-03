"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  BookOpenCheck,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  ExternalLink,
  FileCheck2,
  FilterX,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  X
} from "lucide-react";
import { EvidenceCard } from "@/components/evidence-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  EvidenceDateRange,
  EvidenceDetailState,
  EvidenceExplorerFilters,
  EvidenceLoadState,
  EvidenceRecord,
  EvidenceSnapshot,
  EvidenceSourceType
} from "@/lib/evidence-explorer";
import { evidenceExplorerGateway } from "@/services/evidence-explorer-gateway";

const gateway = evidenceExplorerGateway;

const defaultFilters: EvidenceExplorerFilters = {
  sourceType: "all",
  dateRange: "90d",
  company: "all",
  theme: "ai-infrastructure"
};

const sourceOptions: Array<{ value: "all" | EvidenceSourceType; label: string }> = [
  { value: "all", label: "全部来源" },
  { value: "sec", label: "SEC 文件" },
  { value: "paper", label: "学术论文" },
  { value: "patent", label: "专利" },
  { value: "job", label: "公司招聘" },
  { value: "company_update", label: "公司更新" },
  { value: "social_discussion", label: "社交讨论" }
];

const dateOptions: Array<{ value: EvidenceDateRange; label: string }> = [
  { value: "30d", label: "最近 30 天" },
  { value: "90d", label: "最近 90 天" },
  { value: "1y", label: "最近 1 年" },
  { value: "all", label: "全部时间" }
];

const fallbackCompanyOptions = [
  { value: "all", label: "全部公司与机构" },
  { value: "NVIDIA", label: "NVIDIA" },
  { value: "Microsoft", label: "Microsoft" },
  { value: "Vertiv", label: "Vertiv" },
  { value: "大型云服务商", label: "大型云服务商" },
  { value: "网络设备供应商", label: "网络设备供应商" }
];

const fallbackThemeOptions = [
  { value: "ai-infrastructure", label: "AI 基础设施" },
  { value: "grid-modernization", label: "电网现代化" },
  { value: "semiconductors", label: "半导体" }
];

function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: Array<{ value: string; label: string }>; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted/70">{label}</span>
      <span className="relative mt-2 block">
        <select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 w-full appearance-none rounded-xl border border-line bg-paper pl-3 pr-9 text-sm font-medium text-ink outline-none transition hover:border-ink/20 focus:border-signal focus:ring-2 focus:ring-signal/10">
          {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-3.5 h-4 w-4 text-muted" />
      </span>
    </label>
  );
}

function LoadingTimeline() {
  return (
    <div className="space-y-5">
      {[0, 1, 2].map((item) => (
        <div key={item} className="grid grid-cols-[36px_1fr] gap-4">
          <div className="flex justify-center"><span className="mt-6 h-3 w-3 animate-pulse rounded-full bg-line" /></div>
          <div className="h-[250px] animate-pulse rounded-2xl border border-line bg-paper/70" />
        </div>
      ))}
    </div>
  );
}

function EvidenceDetailPanel({ state, item, error, onRetry }: { state: EvidenceDetailState; item: EvidenceRecord | null; error: string | null; onRetry: () => void }) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/20 backdrop-blur-[2px] data-[state=closed]:animate-out data-[state=open]:animate-in" />
      <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-full overflow-y-auto border-l border-line bg-canvas shadow-[-20px_0_60px_rgba(16,39,61,.12)] outline-none sm:max-w-[620px]">
        <div className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-line bg-canvas/95 px-5 backdrop-blur sm:px-7">
          <div>
            <Dialog.Title className="text-sm font-semibold text-ink">证据核验详情</Dialog.Title>
            <Dialog.Description className="mt-0.5 text-[11px] text-muted">原文、提取事实与主题关联</Dialog.Description>
          </div>
          <Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="关闭证据详情"><X className="h-5 w-5" /></Button></Dialog.Close>
        </div>

        {state === "loading" && <div className="grid min-h-[70vh] place-items-center"><div className="text-center"><LoaderCircle className="mx-auto h-6 w-6 animate-spin text-signal" /><p className="mt-3 text-sm text-muted">正在读取审计后的证据记录</p></div></div>}
        {state === "failed" && <div className="m-7 rounded-2xl border border-red-200 bg-red-50 p-6 text-center"><AlertCircle className="mx-auto h-6 w-6 text-red-700" /><p className="mt-3 font-semibold text-red-800">证据详情读取失败</p><p className="mt-2 text-sm text-red-700">{error}</p><Button variant="outline" className="mt-5" onClick={onRetry}>重新读取</Button></div>}

        {state === "ready" && item && (
          <div className="px-5 py-7 sm:px-8 sm:py-9">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="border-signal/20 bg-signal/[0.07] text-signal"><ShieldCheck className="mr-1 h-3 w-3" />{item.qualityLabel}</Badge>
              <span className="text-xs text-muted">{item.sourceLabel} · {item.id}</span>
            </div>
            <h2 className="mt-5 text-2xl font-semibold leading-9 tracking-[-0.035em] text-ink">{item.title}</h2>
            <p className="mt-4 text-sm leading-7 text-muted">{item.summary}</p>

            <div className="mt-6 grid grid-cols-3 gap-px overflow-hidden rounded-2xl border border-line bg-line">
              <div className="bg-paper p-4"><p className="text-[10px] uppercase tracking-[0.1em] text-muted">来源质量</p><p className="mt-2 text-xl font-semibold text-ink">{Math.round(item.sourceQuality * 100)}</p></div>
              <div className="bg-paper p-4"><p className="text-[10px] uppercase tracking-[0.1em] text-muted">提取置信度</p><p className="mt-2 text-xl font-semibold text-signal">{Math.round(item.confidence * 100)}%</p></div>
              <div className="bg-paper p-4"><p className="text-[10px] uppercase tracking-[0.1em] text-muted">来源层级</p><p className="mt-2 text-sm font-semibold text-ink">{item.primaryOrSecondary === "primary" ? "一级来源" : "二级来源"}</p></div>
            </div>

            <section className="mt-8">
              <div className="flex items-center gap-2"><FileCheck2 className="h-4 w-4 text-signal" /><h3 className="text-sm font-semibold text-ink">提取事实</h3></div>
              <ol className="mt-4 space-y-3">
                {item.extractedFacts.map((fact, index) => <li key={fact} className="grid grid-cols-[28px_1fr] gap-3 rounded-xl border border-line bg-paper p-4 text-sm leading-6 text-ink/85"><span className="font-mono text-xs font-semibold text-signal">{String(index + 1).padStart(2, "0")}</span><span>{fact}</span></li>)}
              </ol>
            </section>

            <section className="mt-8 border-t border-line pt-7">
              <h3 className="text-sm font-semibold text-ink">相关公司与机构</h3>
              <div className="mt-3 flex flex-wrap gap-2">{item.relatedCompanies.map((company) => <span key={company} className="rounded-full border border-line bg-paper px-3 py-1.5 text-xs font-medium text-ink">{company}</span>)}</div>
            </section>

            <section className="mt-7">
              <h3 className="text-sm font-semibold text-ink">相关主题</h3>
              <div className="mt-3 flex flex-wrap gap-2">{item.relatedThemes.map((theme) => <span key={theme.id} className="rounded-full border border-signal/20 bg-signal/[0.06] px-3 py-1.5 text-xs font-medium text-signal">{theme.label}</span>)}</div>
            </section>

            <section className="mt-8 rounded-2xl border border-line bg-paper p-5">
              <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted">Original URL</p>
              <p className="mt-2 break-all text-xs leading-5 text-muted">{item.originalUrl}</p>
              <Button className="mt-4 w-full" asChild><a href={item.originalUrl} target="_blank" rel="noreferrer">打开原始来源<ExternalLink className="h-4 w-4" /></a></Button>
            </section>
          </div>
        )}
      </Dialog.Content>
    </Dialog.Portal>
  );
}

export function EvidenceExplorerWorkspace() {
  const [filters, setFilters] = useState<EvidenceExplorerFilters>(defaultFilters);
  const [loadState, setLoadState] = useState<EvidenceLoadState>("idle");
  const [snapshot, setSnapshot] = useState<EvidenceSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [detailState, setDetailState] = useState<EvidenceDetailState>("closed");
  const [detail, setDetail] = useState<EvidenceRecord | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [companyOptions,setCompanyOptions]=useState(fallbackCompanyOptions);
  const [themeOptions,setThemeOptions]=useState(fallbackThemeOptions);
  const detailRequest = useRef(0);

  useEffect(()=>{ fetch("/api/evidence/facets").then((response)=>response.json()).then((payload:{companies:string[];themes:Array<{id:string;label:string}>})=>{
    if(payload.companies.length)setCompanyOptions([{value:"all",label:"全部公司与机构"},...payload.companies.map((item)=>({value:item,label:item}))]);
    if(payload.themes.length)setThemeOptions(payload.themes.map((item)=>({value:item.id,label:item.label})));
  }).catch(()=>undefined); },[]);

  useEffect(() => {
    let active = true;
    setLoadState(snapshot ? "refreshing" : "loading");
    setError(null);
    gateway.listEvidence(filters)
      .then((nextSnapshot) => { if (active) { setSnapshot(nextSnapshot); setLoadState(nextSnapshot.state); } })
      .catch((reason) => { if (active) { setError(reason instanceof Error ? reason.message : "证据列表读取失败。"); setLoadState("failed"); } });
    return () => { active = false; };
    // refreshKey 代表未来后端的显式重新拉取动作。
  }, [filters, refreshKey]);

  const groupedEvidence = useMemo(() => {
    const groups = new Map<string, EvidenceRecord[]>();
    for (const item of snapshot?.evidence ?? []) {
      const key = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "short" }).format(new Date(item.publishedAt));
      groups.set(key, [...(groups.get(key) ?? []), item]);
    }
    return [...groups.entries()];
  }, [snapshot]);

  const activeFilterCount = Object.entries(filters).filter(([key, value]) => value !== defaultFilters[key as keyof EvidenceExplorerFilters]).length;

  function updateFilter<Key extends keyof EvidenceExplorerFilters>(key: Key, value: EvidenceExplorerFilters[Key]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function loadEvidenceDetail(evidenceId: string) {
    const requestId = ++detailRequest.current;
    setSelectedEvidenceId(evidenceId);
    setDetailState("loading");
    setDetail(null);
    setDetailError(null);
    gateway.getEvidence(evidenceId)
      .then((record) => { if (requestId === detailRequest.current) { setDetail(record); setDetailState("ready"); } })
      .catch((reason) => { if (requestId === detailRequest.current) { setDetailError(reason instanceof Error ? reason.message : "证据详情读取失败。"); setDetailState("failed"); } });
  }

  function closeDetail() {
    detailRequest.current += 1;
    setSelectedEvidenceId(null);
    setDetailState("closed");
    setDetail(null);
  }

  const confidenceLabel = snapshot?.confidenceLevel === "high" ? "高" : snapshot?.confidenceLevel === "medium" ? "中" : snapshot?.confidenceLevel === "low" ? "低" : "—";

  return (
    <div className="mx-auto max-w-[1500px] px-5 py-10 sm:px-8 sm:py-14 xl:px-12">
      <header className="border-b border-line pb-9">
        <div className="flex flex-wrap items-center gap-2"><Badge className="border-signal/20 bg-signal/[0.07] text-signal"><BookOpenCheck className="mr-1 h-3 w-3" />Evidence chain</Badge><span className="text-xs text-muted">仅展示相关且已分配主题的审计证据</span></div>
        <div className="mt-6 grid gap-7 xl:grid-cols-[minmax(0,1fr)_360px] xl:items-end">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">Theme · 当前研究主题</p>
            <h1 className="mt-3 text-[clamp(2.5rem,5vw,4.7rem)] font-semibold leading-[1.02] tracking-[-0.058em] text-ink">{snapshot?.themeLabel ?? "AI 基础设施"}</h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-muted">沿时间线查看系统判断的证据来源、事实边界与交叉验证强度。</p>
            <p className="mt-1 text-xs text-muted/70">See where the judgment comes from.</p>
          </div>
          <div className="rounded-2xl border border-line bg-paper p-5 shadow-card">
            <div className="flex items-start justify-between">
              <div><p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted">证据置信度</p><p className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-signal">{confidenceLabel}</p></div>
              <span className="grid h-10 w-10 place-items-center rounded-full bg-signal/[0.08] text-signal"><ShieldCheck className="h-5 w-5" /></span>
            </div>
            <div className="mt-5 grid grid-cols-3 gap-3 border-t border-line pt-4 text-xs">
              <div><p className="font-semibold text-ink">{snapshot?.evidence.length ?? "—"}</p><p className="mt-1 text-muted">有效证据</p></div>
              <div><p className="font-semibold text-ink">{snapshot?.primarySourceCount ?? "—"}</p><p className="mt-1 text-muted">一级来源</p></div>
              <div><p className="font-semibold text-ink">{snapshot?.sourceTypeCount ?? "—"}</p><p className="mt-1 text-muted">来源类型</p></div>
            </div>
          </div>
        </div>
      </header>

      <div className="mt-8 grid items-start gap-8 xl:grid-cols-[minmax(0,1fr)_300px]">
        <main>
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-signal">Timeline view</p><h2 className="mt-1 text-xl font-semibold tracking-[-0.025em] text-ink">证据时间线</h2></div>
            <div className="flex items-center gap-2"><span className="text-xs text-muted">{snapshot ? `${snapshot.evidence.length} / ${snapshot.totalBeforeFilters} 条证据` : "正在读取证据"}</span><Button variant="ghost" size="icon" onClick={() => setRefreshKey((value) => value + 1)} aria-label="刷新证据"><RefreshCw className={loadState === "refreshing" ? "h-4 w-4 animate-spin" : "h-4 w-4"} /></Button></div>
          </div>

          {(loadState === "idle" || loadState === "loading") && <LoadingTimeline />}
          {loadState === "failed" && <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center"><AlertCircle className="mx-auto h-7 w-7 text-red-700" /><p className="mt-3 font-semibold text-red-800">证据时间线暂时无法读取</p><p className="mt-2 text-sm text-red-700">{error}</p><Button variant="outline" className="mt-5" onClick={() => setRefreshKey((value) => value + 1)}>重新加载</Button></div>}
          {loadState === "empty" && <div className="rounded-2xl border border-dashed border-ink/20 bg-paper px-6 py-16 text-center"><FilterX className="mx-auto h-8 w-8 text-muted" /><h3 className="mt-4 text-xl font-semibold text-ink">当前条件下没有有效证据</h3><p className="mt-2 text-sm text-muted">调整来源、日期、公司或主题。无关和待审核记录不会进入时间线。</p><Button variant="outline" className="mt-5" onClick={() => setFilters(defaultFilters)}>清除筛选</Button></div>}

          {snapshot && (loadState === "ready" || loadState === "refreshing") && (
            <div className={loadState === "refreshing" ? "relative opacity-55 transition" : "relative transition"}>
              <span className="absolute bottom-0 left-[17px] top-4 w-px bg-line sm:left-[23px]" aria-hidden="true" />
              <div className="space-y-9">
                {groupedEvidence.map(([date, records]) => (
                  <section key={date}>
                    <div className="relative z-[1] mb-4 grid grid-cols-[36px_1fr] items-center gap-3 sm:grid-cols-[48px_1fr]">
                      <span className="mx-auto grid h-7 w-7 place-items-center rounded-full border border-signal/20 bg-canvas text-signal"><CalendarDays className="h-3.5 w-3.5" /></span>
                      <div className="flex items-center justify-between gap-4"><h3 className="text-xs font-semibold text-ink">{date}</h3><span className="text-[10px] uppercase tracking-[0.1em] text-muted">{records.length} citations</span></div>
                    </div>
                    <div className="space-y-4">
                      {records.map((item) => (
                        <div key={item.id} className="relative grid grid-cols-[36px_1fr] gap-3 sm:grid-cols-[48px_1fr]">
                          <span className="relative z-[1] mx-auto mt-7 h-2.5 w-2.5 rounded-full border-2 border-canvas bg-signal shadow-[0_0_0_1px_rgba(26,113,98,.25)]" />
                          <EvidenceCard item={item} onSelect={loadEvidenceDetail} />
                        </div>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
              {loadState === "refreshing" && <div className="absolute inset-0 grid place-items-start justify-center pt-20"><span className="flex items-center gap-2 rounded-full border border-line bg-paper px-4 py-2 text-xs font-semibold text-ink shadow-card"><LoaderCircle className="h-4 w-4 animate-spin text-signal" />正在更新证据链</span></div>}
            </div>
          )}
        </main>

        <aside className="sticky top-24 rounded-2xl border border-line bg-paper p-5 shadow-card" aria-label="证据筛选">
          <div className="flex items-center justify-between"><div className="flex items-center gap-2"><SlidersHorizontal className="h-4 w-4 text-signal" /><h2 className="text-sm font-semibold text-ink">证据筛选</h2></div>{activeFilterCount > 0 && <Badge className="border-signal/20 bg-signal/[0.07] text-signal">{activeFilterCount}</Badge>}</div>
          <p className="mt-2 text-xs leading-5 text-muted">筛选只改变当前证据视图，不会修改研究结论。</p>
          <div className="mt-6 space-y-5">
            <FilterSelect label="来源类型" value={filters.sourceType} options={sourceOptions} onChange={(value) => updateFilter("sourceType", value as EvidenceExplorerFilters["sourceType"])} />
            <FilterSelect label="发布日期 Date" value={filters.dateRange} options={dateOptions} onChange={(value) => updateFilter("dateRange", value as EvidenceDateRange)} />
            <FilterSelect label="公司 Company" value={filters.company} options={companyOptions} onChange={(value) => updateFilter("company", value)} />
            <FilterSelect label="主题 Theme" value={filters.theme} options={themeOptions} onChange={(value) => updateFilter("theme", value)} />
          </div>
          <Button variant="outline" className="mt-6 w-full" onClick={() => setFilters(defaultFilters)} disabled={activeFilterCount === 0}><FilterX className="h-4 w-4" />清除筛选</Button>
          <div className="mt-6 border-t border-line pt-5">
            <div className="flex items-center gap-2 text-xs font-medium text-ink"><CircleDot className="h-3.5 w-3.5 text-signal" />证据准入规则</div>
            <ul className="mt-3 space-y-2 text-[11px] leading-5 text-muted">
              <li className="flex gap-2"><CheckCircle2 className="mt-1 h-3 w-3 shrink-0 text-signal" />相关性状态为 relevant</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-1 h-3 w-3 shrink-0 text-signal" />主题已完成明确分配</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-1 h-3 w-3 shrink-0 text-signal" />保留可追溯原始 URL</li>
            </ul>
          </div>
        </aside>
      </div>

      <Dialog.Root open={selectedEvidenceId !== null} onOpenChange={(open) => { if (!open) closeDetail(); }}>
        <EvidenceDetailPanel state={detailState} item={detail} error={detailError} onRetry={() => selectedEvidenceId && loadEvidenceDetail(selectedEvidenceId)} />
      </Dialog.Root>
    </div>
  );
}
