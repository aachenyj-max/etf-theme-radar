"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  ArrowUpRight,
  BookOpenCheck,
  Building2,
  CheckCircle2,
  CircleDot,
  Clock3,
  Landmark,
  Link2,
  ListChecks,
  RefreshCw,
  Scale,
  ShieldCheck,
  TriangleAlert
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { MemoCitation, MemoConfidence, MemoDecisionStatus, ReportDetailLoadState, ReportMemoDetail } from "@/lib/report-detail";
import { reportDetailGateway } from "@/services/report-detail-gateway";
import { cn } from "@/lib/utils";
import { labelFor, sourceTypeLabels } from "@/lib/ui-labels";

const statusLabels: Record<MemoDecisionStatus, string> = {
  DEEP_RESEARCH: "深度研究",
  WATCH: "持续观察",
  REJECT: "暂不推进"
};

const confidenceLabels: Record<MemoConfidence, string> = {
  high: "高",
  medium: "中",
  low: "低"
};

const conclusionLabels = {
  supported: "证据支持",
  mixed: "结论混合",
  insufficient: "证据不足"
} as const;

function formatDate(value: string) {
  if (!value) return "尚未记录";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" }).format(new Date(value));
}

function InitialMark({ publisher, logoUrl }: { publisher: string; logoUrl: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <span className="grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-xl border border-line bg-white text-xs font-semibold text-ink shadow-sm">
      {!failed && logoUrl
        ? <img src={logoUrl} alt="" className="h-6 w-6 object-contain" onError={() => setFailed(true)} />
        : publisher.slice(0, 2).toUpperCase()}
    </span>
  );
}

function MemoList({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <p className="text-sm leading-6 text-muted">{empty}</p>;
  return (
    <ul className="space-y-3">
      {items.map((item, index) => (
        <li key={`${item}-${index}`} className="flex gap-3 text-sm leading-6 text-ink/85">
          <span className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-signal" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function SourceButton({ url, publisher = "来源" }: { url: string; publisher?: string }) {
  if (!url) return null;
  let domain = publisher;
  try { domain = new URL(url).hostname.replace(/^www\./, ""); } catch {}
  return (
    <a href={url} target="_blank" rel="noreferrer" title={domain} aria-label={`打开 ${publisher} 来源`}
      className="inline-flex items-center gap-1 rounded-full border border-ink/10 bg-ink/[0.045] px-2.5 py-1 text-[10px] font-semibold text-ink/65 transition hover:border-signal/25 hover:bg-signal/[0.08] hover:text-signal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/30">
      来源 <ArrowUpRight className="h-3 w-3" />
    </a>
  );
}

function EvidenceMemo({ citation, number }: { citation: MemoCitation; number: number }) {
  return (
    <article id={citation.id} className="scroll-mt-24 border-t border-line py-7 first:border-t-0 first:pt-0">
      <div className="flex items-start gap-4">
        <InitialMark publisher={citation.publisher} logoUrl={citation.logoUrl} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-mono text-[10px] tracking-[0.12em] text-signal">{String(number).padStart(2, "0")}</span>
            <span className="text-xs font-semibold text-ink">{citation.publisher}</span>
            <span className="text-[11px] text-muted">{labelFor(sourceTypeLabels, citation.sourceType, "公开来源")}</span>
            <span className="ml-auto text-[11px] text-muted">置信度 {Math.round(citation.confidence * 100)}%</span>
          </div>
          <h3 className="mt-3 text-lg font-semibold leading-7 tracking-[-0.02em] text-ink">{citation.claim}</h3>
          <p className="mt-3 text-sm leading-7 text-ink/78">{citation.evidence}</p>
          <div className="mt-4 flex gap-2 rounded-xl bg-amber/[0.07] px-3.5 py-3 text-xs leading-5 text-ink/70">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber" />
            <span><strong className="font-semibold text-ink">证据边界：</strong>{citation.limitation}</span>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-4">
            <SourceButton url={citation.url} publisher={citation.publisher} />
          </div>
        </div>
      </div>
    </article>
  );
}

function CounterArgumentColumn({ items }: { items: ReportMemoDetail["bearCase"]["counterArguments"] }) {
  if (!items.length) return <p className="text-sm leading-6 text-muted">尚未检索到足够的独立反方证据。</p>;
  return (
    <ul className="space-y-4">
      {items.map((item, index) => {
        const argument = typeof item === "string" ? { claim: item, reason: "", sourceUrl: "", publisher: "公开来源" } : item;
        return <li key={`${argument.claim}-${index}`} className="border-l-2 border-amber/35 pl-3">
          <p className="text-sm font-medium leading-6 text-ink/85">{argument.claim}</p>
          {argument.reason && <p className="mt-1 text-xs leading-5 text-muted">{argument.reason}</p>}
          <div className="mt-2"><SourceButton url={argument.sourceUrl} publisher={argument.publisher} /></div>
        </li>;
      })}
    </ul>
  );
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined) return "未核验";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function formatMoney(value?: number | null, currency = "USD") {
  if (value === null || value === undefined) return "未核验";
  try {
    return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1, style: "currency", currency }).format(value);
  } catch {
    return `${currency} ${new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value)}`;
  }
}

function EtfMarketCard({ product }: { product: NonNullable<ReportMemoDetail["etfLandscape"]["products"]>[number] }) {
  const available = product.data_status === "available" || product.data_status === "partial";
  return (
    <article className="overflow-hidden rounded-2xl border border-line bg-paper shadow-card">
      <div className="flex items-start justify-between gap-4 border-b border-line bg-ink/[0.025] px-5 py-4">
        <div><p className="font-mono text-xl font-semibold tracking-[-0.04em] text-ink">{product.ticker}</p><p className="mt-1 text-[11px] text-muted">{product.issuer} · {product.category}</p>{(product.exchange || product.listing_market) && <p className="mt-1 text-[10px] text-muted">{[product.listing_market, product.exchange].filter(Boolean).join(" · ")}</p>}</div>
        <Badge className={product.price_trend === "up" ? "border-signal/20 bg-signal/[0.08] text-signal" : product.price_trend === "down" ? "border-red-200 bg-red-50 text-red-700" : ""}>{product.price_trend === "up" ? "走强" : product.price_trend === "down" ? "走弱" : available ? "震荡" : "未核验"}</Badge>
      </div>
      <div className="p-5">
        <div className="flex items-end justify-between gap-4">
          <div><p className="text-[10px] uppercase tracking-[0.14em] text-muted">Last close</p><p className="mt-1 text-2xl font-semibold text-ink">{product.last_close === undefined ? "—" : formatMoney(product.last_close, product.currency)}</p></div>
          <p className="text-right text-[10px] text-muted">{product.as_of ? formatDate(product.as_of) : "暂无行情日期"}</p>
        </div>
        <dl className="mt-5 grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-line bg-line text-center">
          {(["1w", "1m", "3m"] as const).map((period) => <div key={period} className="bg-paper px-2 py-3"><dt className="text-[9px] uppercase text-muted">{period}</dt><dd className={cn("mt-1 text-xs font-semibold", (product.returns?.[period] ?? 0) > 0 ? "text-signal" : (product.returns?.[period] ?? 0) < 0 ? "text-red-700" : "text-ink")}>{formatPercent(product.returns?.[period])}</dd></div>)}
        </dl>
        <dl className="mt-4 grid gap-2 text-[11px] sm:grid-cols-2">
          <div className="flex justify-between gap-3"><dt className="text-muted">3月最大回撤</dt><dd className="font-medium text-ink">{formatPercent(product.max_drawdown_3m)}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-muted">3月年化波动</dt><dd className="font-medium text-ink">{formatPercent(product.annualized_volatility_3m)}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-muted">20日平均成交额</dt><dd className="font-medium text-ink">{formatMoney(product.average_dollar_volume_20d, product.currency)}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-muted">成交活跃度</dt><dd className="font-medium text-ink">{product.activity_trend === "higher" ? "升温" : product.activity_trend === "lower" ? "降温" : available ? "平稳" : "未核验"}</dd></div>
        </dl>
        <div className="mt-4 flex items-center justify-between border-t border-line pt-3"><span className="text-[10px] text-muted">不代表买入人数或资金净流入</span><SourceButton url={product.source_url} publisher={product.ticker} /></div>
      </div>
    </article>
  );
}

function SourceLogo({ name, logoUrl, fallback }: { name: string; logoUrl: string; fallback: string }) {
  const [failed, setFailed] = useState(false);
  return <span className="grid h-9 w-9 place-items-center overflow-hidden rounded-full border-2 border-paper bg-canvas text-[10px] font-bold text-ink shadow-sm">
    {!failed && logoUrl ? <img src={logoUrl} alt="" className="h-5 w-5 object-contain" onError={() => setFailed(true)} /> : fallback}
  </span>;
}

function CitationPanel({ citations, report, refreshing, refreshError, onRefresh }: {
  citations: MemoCitation[]; report: ReportMemoDetail; refreshing: boolean;
  refreshError: string; onRefresh: () => void;
}) {
  const snapshot = report.latestMarketSnapshot ?? {
    origin: report.etfLandscape.products?.length ? "legacy_report_snapshot" as const : "unavailable" as const,
    market_as_of: report.etfLandscape.marketAsOf,
    status: report.etfLandscape.marketSnapshotStatus,
    products: report.etfLandscape.products ?? [],
  };
  const marketProducts = snapshot.products ?? [];
  return (
    <aside className="xl:sticky xl:top-6 xl:self-start">
      <div className="overflow-hidden rounded-2xl border border-line bg-ink text-paper shadow-card">
        <div className="flex items-center justify-between border-b border-paper/10 px-5 py-4">
          <div><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#8FD5C7]">ETF now</p><h2 className="mt-1 text-base font-semibold">ETF 现状</h2></div>
          <Button size="sm" variant="ghost" className="text-paper hover:bg-paper/10 hover:text-paper" disabled={refreshing} onClick={onRefresh}><RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />刷新</Button>
        </div>
        <div className="px-5 py-4">
          <div className="flex items-center justify-between text-[10px] text-paper/55">
            <span>{snapshot?.origin === "independent_snapshot" ? `快照 ${snapshot.snapshot_id?.slice(0, 8)}` : snapshot?.origin === "legacy_report_snapshot" ? "旧报告行情" : "尚无行情"}</span>
            <span>{snapshot?.market_as_of ? `截至 ${formatDate(snapshot.market_as_of)}` : "日期未知"}</span>
          </div>
          {marketProducts.length ? <div className="mt-3 divide-y divide-paper/10">{marketProducts.slice(0, 6).map((product) => {
            const stale = product.data_status === "stale" || product.error;
            return <div key={product.ticker} className="grid grid-cols-[48px_1fr_auto] items-center gap-2 py-3 text-xs">
              <span className="font-mono font-semibold text-paper">{product.ticker}</span>
              <div><p className="font-semibold text-paper/90">{product.last_close === undefined ? "暂不可用" : formatMoney(product.last_close, product.currency)}</p><p className="mt-0.5 text-[9px] text-paper/45">{stale ? "缓存数据" : product.as_of ? formatDate(product.as_of) : "日期未知"}</p></div>
              <div className="text-right"><p className={cn("font-semibold", (product.returns?.["1m"] ?? 0) > 0 ? "text-[#8FD5C7]" : (product.returns?.["1m"] ?? 0) < 0 ? "text-red-300" : "text-paper/75")}>{formatPercent(product.returns?.["1m"])}</p><p className="mt-0.5 text-[9px] text-paper/45">{product.activity_trend === "higher" ? "活跃度升温" : product.activity_trend === "lower" ? "活跃度降温" : "活跃度平稳"}</p></div>
            </div>;
          })}</div> : <p className="mt-4 text-xs leading-5 text-paper/55">暂无成功行情快照。手动刷新后会在此显示，且不会改变报告版本。</p>}
          <p className="mt-3 flex gap-1 border-t border-paper/10 pt-3 text-[9px] leading-4 text-paper/40"><span>成交活跃度</span><span>不代表买入人数或资金净流入</span></p>
          {refreshError && <p className="mt-3 rounded-lg bg-red-400/10 p-2 text-[10px] text-red-200">{refreshError}</p>}
        </div>
      </div>
      <div className="mt-4 rounded-2xl border border-line bg-paper p-5 shadow-card">
        <div className="flex items-center justify-between border-b border-line pb-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-signal">Citation Panel</p>
            <h2 className="mt-1 text-base font-semibold text-ink">全部来源</h2>
          </div>
          <span className="font-mono text-xs text-muted">{String(citations.length).padStart(2, "0")}</span>
        </div>
        {citations.length ? (
          <ol className="mt-2">
            {citations.map((citation, index) => (
              <li key={citation.id} className="border-b border-line py-4 last:border-b-0">
                <div className="flex gap-3">
                  <span className="font-mono text-[10px] text-signal">{String(index + 1).padStart(2, "0")}</span>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold leading-5 text-ink">{citation.publisher}</p>
                    <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-muted">{citation.claim}</p>
                    <div className="mt-2 flex items-center gap-3">
                      <a href={`#${citation.id}`} className="text-[10px] font-semibold text-signal hover:underline">定位正文</a>
                      <a href={citation.url} target="_blank" rel="noreferrer" aria-label={`打开 ${citation.publisher} 原文`} className="text-muted hover:text-ink"><ArrowUpRight className="h-3.5 w-3.5" /></a>
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <div className="py-8 text-center">
            <Link2 className="mx-auto h-5 w-5 text-muted" />
            <p className="mt-3 text-xs leading-5 text-muted">当前版本尚无可核验的正文引用。</p>
          </div>
        )}
      </div>
      <div className="mt-4 rounded-2xl border border-line bg-canvas p-4 text-[11px] leading-5 text-muted">
        <div className="flex items-center gap-2 font-semibold text-ink"><ShieldCheck className="h-4 w-4 text-signal" />研究边界</div>
        <p className="mt-2">本页用于主题研究与证据核验，不构成投资、交易、组合或 ETF 产品建议。</p>
      </div>
    </aside>
  );
}

function LoadingMemo() {
  return (
    <div className="mx-auto max-w-[1480px] animate-pulse px-5 py-10 sm:px-8 xl:px-12">
      <div className="h-4 w-32 rounded bg-ink/10" />
      <div className="mt-12 h-16 max-w-3xl rounded-2xl bg-ink/[0.06]" />
      <div className="mt-10 grid gap-7 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-5">{[260, 420, 340].map((height) => <div key={height} style={{ height }} className="rounded-2xl border border-line bg-paper" />)}</div>
        <div className="h-[460px] rounded-2xl border border-line bg-paper" />
      </div>
    </div>
  );
}

function DataColumn({ title, eyebrow, items, empty }: { title: string; eyebrow: string; items: string[]; empty: string }) {
  return (
    <div className="min-h-[180px] border-t-2 border-ink pt-4">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{eyebrow}</p>
      <h3 className="mt-2 text-base font-semibold text-ink">{title}</h3>
      <div className="mt-4"><MemoList items={items} empty={empty} /></div>
    </div>
  );
}

export function ReportDetailWorkspace({ reportId }: { reportId: string }) {
  const [state, setState] = useState<ReportDetailLoadState>("idle");
  const [report, setReport] = useState<ReportMemoDetail | null>(null);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [versions, setVersions] = useState<Array<{version:number;content_hash:string;created_at:string}>>([]);
  const [versionDiff, setVersionDiff] = useState<{added:string[];removed:string[]}|null>(null);
  const [marketRefreshing, setMarketRefreshing] = useState(false);
  const [marketRefreshError, setMarketRefreshError] = useState("");

  const load = useCallback(() => {
    setState((current) => current === "ready" ? "refreshing" : "loading");
    setError("");
    reportDetailGateway.getReportDetail(reportId)
      .then((value) => { setReport(value); setState("ready"); })
      .catch((reason: Error & { status?: number }) => {
        setError(reason.message || "报告读取失败。");
        setState(reason.status === 404 ? "not_found" : "failed");
      });
  }, [reportId]);

  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => {
    void fetch(`/api/reports/${encodeURIComponent(reportId)}/versions`).then((response)=>response.ok?response.json():Promise.reject()).then((payload:{versions:Array<{version:number;content_hash:string;created_at:string}>})=>setVersions(payload.versions)).catch(()=>setVersions([]));
  },[reportId,refreshKey]);
  async function compareLatestVersions(){
    if(versions.length<2)return;
    const response=await fetch(`/api/reports/${encodeURIComponent(reportId)}/compare?left=${versions[1].version}&right=${versions[0].version}`);
    if(response.ok)setVersionDiff(await response.json() as {added:string[];removed:string[]});
  }
  async function refreshMarketSnapshot() {
    setMarketRefreshing(true); setMarketRefreshError("");
    try {
      const { runId } = await reportDetailGateway.refreshMarketSnapshot(reportId);
      for (let attempt = 0; attempt < 120; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const response = await fetch(`/api/research-runs/${encodeURIComponent(runId)}`);
        if (!response.ok) throw new Error(`刷新任务返回 ${response.status}`);
        const run = await response.json() as { status: string; error?: string };
        if (run.status === "completed") { setRefreshKey((value) => value + 1); return; }
        if (["failed", "cancelled", "blocked_configuration"].includes(run.status)) throw new Error(run.error || "市场快照刷新失败");
      }
      throw new Error("市场快照刷新超时，请稍后重新加载报告。");
    } catch (reason) {
      setMarketRefreshError(reason instanceof Error ? reason.message : "市场快照刷新失败");
    } finally { setMarketRefreshing(false); }
  }

  const citations = useMemo(() => report ? [...report.bullCase, ...report.bearCase.citations] : [], [report]);

  if (state === "idle" || state === "loading") return <LoadingMemo />;
  if (!report || state === "failed" || state === "not_found") {
    return (
      <div className="mx-auto max-w-3xl px-6 py-24 text-center">
        <AlertCircle className="mx-auto h-8 w-8 text-amber" />
        <h1 className="mt-5 text-2xl font-semibold text-ink">{state === "not_found" ? "这份研究报告不存在" : "暂时无法读取报告"}</h1>
        <p className="mt-3 text-sm text-muted">{error}</p>
        <div className="mt-7 flex justify-center gap-3">
          <Button variant="outline" asChild><Link href="/reports"><ArrowLeft className="h-4 w-4" />返回报告库</Link></Button>
          <Button onClick={() => setRefreshKey((value) => value + 1)}><RefreshCw className="h-4 w-4" />重新加载</Button>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("mx-auto max-w-[1480px] px-5 py-8 sm:px-8 sm:py-12 xl:px-12", state === "refreshing" && "opacity-70 transition")}>
      <nav className="flex items-center justify-between">
        <Link href="/reports" className="inline-flex items-center gap-2 text-xs font-semibold text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" />返回研究资料库</Link>
        <Button variant="ghost" size="sm" onClick={() => setRefreshKey((value) => value + 1)} disabled={state === "refreshing"}>
          <RefreshCw className={cn("h-3.5 w-3.5", state === "refreshing" && "animate-spin")} />同步最新版本
        </Button>
      </nav>

      <header className="mt-8 border-b border-line pb-9">
        <div className="flex flex-wrap items-center gap-2">
          <Badge className="border-signal/20 bg-signal/[0.07] text-signal">{report.themeLabel}</Badge>
          <Badge className="border-ink/15 bg-ink/[0.04] text-ink">{statusLabels[report.status]}</Badge>
          <span className="text-xs text-muted">置信度：<strong className="font-semibold text-ink">{confidenceLabels[report.confidence]}</strong></span>
        </div>
        <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-signal">Investment Committee Memo</p>
            <h1 className="mt-3 max-w-5xl text-[clamp(2.3rem,5vw,4.5rem)] font-semibold leading-[1.03] tracking-[-0.055em] text-ink">{report.title}</h1>
          </div>
          <dl className="grid grid-cols-2 gap-x-8 gap-y-3 border-l-2 border-signal pl-5 text-xs">
            <div><dt className="text-muted">最后更新</dt><dd className="mt-1 font-semibold text-ink">{formatDate(report.lastUpdated)}</dd></div>
            <div><dt className="text-muted">报告版本</dt><dd className="mt-1 font-semibold text-ink">V{report.version}</dd></div>
            <div><dt className="text-muted">研究审计</dt><dd className="mt-1 font-semibold text-ink">{report.auditPassed ? "已通过" : "待复核"}</dd></div>
            <div><dt className="text-muted">当前状态</dt><dd className="mt-1 font-semibold text-signal">{statusLabels[report.status]}</dd></div>
          </dl>
        </div>
      </header>
      <section className="mt-6 rounded-2xl border border-line bg-paper p-5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-signal">Immutable history</p><h2 className="mt-1 text-base font-semibold text-ink">报告版本</h2></div>
          <div className="flex items-center gap-5">
            <div>
              <p className="text-right text-[9px] font-semibold uppercase tracking-[.12em] text-muted">本次研究来源</p>
              <div className="mt-2 flex justify-end -space-x-2">
                {(report.researchSources ?? []).slice(0, 8).map((source) => <a key={source.id} href={source.url} target="_blank" rel="noreferrer" title={`${source.name} · ${source.citationCount} 条引用`} aria-label={`打开 ${source.name} 来源，${source.citationCount} 条引用`} className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal"><SourceLogo name={source.name} logoUrl={source.logoUrl} fallback={source.fallback} /></a>)}
                {(report.researchSources?.length ?? 0) > 8 && <span className="grid h-9 w-9 place-items-center rounded-full border-2 border-paper bg-ink text-[9px] font-semibold text-paper">+{(report.researchSources?.length ?? 0) - 8}</span>}
                {!report.researchSources?.length && <span className="text-[10px] text-muted">暂无结构化来源</span>}
              </div>
            </div>
            <Button variant="outline" size="sm" disabled={versions.length<2} onClick={()=>void compareLatestVersions()}>比较最近两个版本</Button>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">{versions.map((version)=><Badge key={version.version}>V{version.version} · {version.content_hash.slice(0,8)}</Badge>)}{versions.length===0&&<p className="text-xs text-muted">当前报告尚无版本快照。</p>}</div>
        {versionDiff&&<div className="mt-4 grid gap-4 text-xs md:grid-cols-2"><div className="rounded-xl bg-signal/[.06] p-3"><p className="font-semibold text-ink">新增 {versionDiff.added.length} 行</p>{versionDiff.added.slice(0,5).map((line,index)=><p key={index} className="mt-1 line-clamp-2 text-muted">+ {line}</p>)}</div><div className="rounded-xl bg-amber/[.07] p-3"><p className="font-semibold text-ink">移除 {versionDiff.removed.length} 行</p>{versionDiff.removed.slice(0,5).map((line,index)=><p key={index} className="mt-1 line-clamp-2 text-muted">− {line}</p>)}</div></div>}
      </section>

      <div className="mt-9 grid gap-8 xl:grid-cols-[minmax(0,1fr)_300px]">
        <main className="min-w-0">
          <section aria-labelledby="research-conclusion" className="relative overflow-hidden rounded-2xl border border-ink/15 bg-ink px-6 py-7 text-paper shadow-card sm:px-8">
            <div className={cn(
              "absolute inset-y-0 left-0 w-1.5",
              report.conclusion.verdict === "supported" ? "bg-signal" : report.conclusion.verdict === "mixed" ? "bg-amber" : "bg-paper/35"
            )} />
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-paper/55">Evidence verdict</p>
                <h2 id="research-conclusion" className="mt-2 text-xl font-semibold tracking-[-0.025em]">研究结论</h2>
              </div>
              <div className="flex items-center gap-2">
                <span className="rounded-full border border-paper/15 bg-paper/[0.08] px-3 py-1 text-xs font-semibold">{conclusionLabels[report.conclusion.verdict]}</span>
                <span className="text-xs text-paper/60">置信度 {confidenceLabels[report.conclusion.confidence]}</span>
              </div>
            </div>
            <p className="mt-6 max-w-4xl text-lg leading-8 text-paper/90">{report.conclusion.statement}</p>
            {report.conclusion.limitations.length > 0 && (
              <div className="mt-6 border-t border-paper/12 pt-4">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-paper/45">结论边界</p>
                <p className="mt-2 text-xs leading-6 text-paper/65">{report.conclusion.limitations.slice(0, 3).join("；")}</p>
              </div>
            )}
          </section>

          <section className="mt-10">
            <div className="flex items-center gap-3"><span className="font-mono text-xs text-signal">01</span><h2 className="text-xl font-semibold tracking-[-0.025em] text-ink">执行摘要</h2></div>
            <p className="mt-5 max-w-4xl text-lg leading-8 text-ink/82">{report.executiveSummary}</p>
          </section>

          <section className="mt-10 rounded-2xl border border-line bg-paper p-6 shadow-card sm:p-8">
            <div className="flex items-center gap-3"><BookOpenCheck className="h-5 w-5 text-signal" /><div><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">Investment Thesis</p><h2 className="mt-1 text-xl font-semibold text-ink">投资假设</h2></div></div>
            <p className="mt-6 border-l-2 border-signal pl-5 text-base leading-8 text-ink">{report.investmentThesis}</p>
            <div className="mt-8 grid gap-7 border-t border-line pt-7 lg:grid-cols-3">
              <DataColumn eyebrow="Why now" title="为什么是现在" items={report.whyNow} empty="暂无可审计的时间催化因素。" />
              <DataColumn eyebrow="Key drivers" title="关键驱动" items={report.keyDrivers} empty="尚未形成明确驱动机制。" />
              <DataColumn eyebrow="Main risks" title="核心风险" items={report.mainRisks} empty="风险数据尚待补充。" />
            </div>
          </section>

          <section className="mt-12">
            <div className="flex items-end justify-between border-b border-ink pb-4">
              <div><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-signal">Bull Case</p><h2 className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-ink">支持证据</h2></div>
              <span className="text-xs text-muted">{report.bullCase.length} 条审计后证据</span>
            </div>
            <div className="mt-7">
              {report.bullCase.length
                ? report.bullCase.map((citation, index) => <EvidenceMemo key={citation.id} citation={citation} number={index + 1} />)
                : <div className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">当前报告没有满足正文引用要求的支持证据。</div>}
            </div>
          </section>

          <section className="mt-12 rounded-2xl border border-line bg-[#F7F5F0] p-6 sm:p-8">
            <div className="flex items-center gap-3"><Scale className="h-5 w-5 text-amber" /><div><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-amber">Bear Case</p><h2 className="mt-1 text-2xl font-semibold text-ink">反方论证与证据缺口</h2></div></div>
            <div className="mt-7 grid gap-7 lg:grid-cols-3">
              <div className="min-h-[180px] border-t-2 border-ink pt-4"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">Counter arguments</p><h3 className="mt-2 text-base font-semibold text-ink">反方观点</h3><div className="mt-4"><CounterArgumentColumn items={report.bearCase.counterArguments} /></div></div>
              <DataColumn eyebrow="Risks" title="失效风险" items={report.bearCase.risks} empty="尚未完成系统性风险映射。" />
              <DataColumn eyebrow="Missing data" title="缺失数据" items={report.bearCase.missingData} empty="当前未记录新增数据缺口。" />
            </div>
            {report.bearCase.citations.length > 0 && <div className="mt-8 border-t border-line pt-7">{report.bearCase.citations.map((citation, index) => <EvidenceMemo key={citation.id} citation={citation} number={report.bullCase.length + index + 1} />)}</div>}
          </section>

          <section className="mt-12">
            <div className="flex items-center justify-between border-b border-line pb-4">
              <div className="flex items-center gap-3"><Landmark className="h-5 w-5 text-signal" /><h2 className="text-2xl font-semibold tracking-[-0.03em] text-ink">ETF 市场格局</h2></div>
              <Badge>冻结于报告 V{report.version}</Badge>
            </div>
            <p className="mt-4 text-[11px] leading-5 text-muted">竞品、持仓重叠和产品空白保持报告版本冻结内容；最新价格与交易活跃度在右侧“ETF 现状”独立刷新。</p>
            <div className="mt-7 grid gap-7 lg:grid-cols-3">
              <DataColumn eyebrow="Existing ETFs" title="现有 ETF" items={report.etfLandscape.existingEtfs} empty="暂无已验证的竞品清单。" />
              <DataColumn eyebrow="Overlap" title="持仓重叠" items={report.etfLandscape.overlap === "unknown" ? [] : [report.etfLandscape.overlap]} empty="unknown：尚未完成持仓穿透。" />
              <DataColumn eyebrow="White space" title="产品空白" items={report.etfLandscape.whiteSpace === "unknown" ? [] : [report.etfLandscape.whiteSpace]} empty="unknown：数据不足，不判断产品空白。" />
            </div>
          </section>

          <section className="mt-12">
            <div className="flex items-center justify-between border-b border-line pb-4">
              <div className="flex items-center gap-3"><Building2 className="h-5 w-5 text-signal" /><h2 className="text-2xl font-semibold tracking-[-0.03em] text-ink">公司映射</h2></div>
              <Badge>{report.companyMap.dataStatus === "unknown" ? "待建立映射" : "初步映射"}</Badge>
            </div>
            <div className="mt-7 grid gap-7 lg:grid-cols-3">
              <DataColumn eyebrow="Pure plays" title="纯主题公司" items={report.companyMap.purePlays} empty="待完成收入暴露与纯度核验。" />
              <DataColumn eyebrow="Enablers" title="基础设施赋能者" items={report.companyMap.enablers} empty="暂无已审计的公司映射。" />
              <DataColumn eyebrow="Beneficiaries" title="潜在受益者" items={report.companyMap.beneficiaries} empty="暂无已审计的受益公司分类。" />
            </div>
          </section>

          <section className="mt-12 overflow-hidden rounded-2xl bg-ink text-white">
            <div className="grid lg:grid-cols-[280px_minmax(0,1fr)]">
              <div className="border-b border-white/10 p-7 lg:border-b-0 lg:border-r">
                <p className="text-[10px] font-semibold uppercase tracking-[0.17em] text-white/55">Current Decision</p>
                <p className="mt-5 text-3xl font-semibold tracking-[-0.04em]">{statusLabels[report.decision.currentStatus]}</p>
                <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-white/15 px-3 py-1.5 text-xs text-white/75"><CircleDot className="h-3.5 w-3.5 text-[#8FD5C7]" />当前研究状态</div>
              </div>
              <div className="p-7 sm:p-9">
                <p className="text-sm leading-7 text-white/80">{report.decision.rationale}</p>
                <div className="mt-7 border-t border-white/10 pt-6">
                  <div className="flex items-center gap-2 text-sm font-semibold"><ListChecks className="h-4 w-4 text-[#8FD5C7]" />下一步行动</div>
                  <ol className="mt-4 grid gap-3 sm:grid-cols-2">
                    {report.decision.nextActions.map((action, index) => <li key={action} className="flex gap-3 text-xs leading-5 text-white/72"><span className="font-mono text-[#8FD5C7]">{String(index + 1).padStart(2, "0")}</span>{action}</li>)}
                  </ol>
                </div>
              </div>
            </div>
          </section>

          <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5 text-[11px] text-muted">
            <span className="inline-flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-signal" />所有正文引用均由结构化证据记录注入</span>
            <span className="inline-flex items-center gap-2"><Clock3 className="h-3.5 w-3.5" />版本 V{report.version} · {formatDate(report.lastUpdated)}</span>
          </footer>
        </main>
        <CitationPanel citations={citations} report={report} refreshing={marketRefreshing} refreshError={marketRefreshError} onRefresh={() => void refreshMarketSnapshot()} />
      </div>
    </div>
  );
}
