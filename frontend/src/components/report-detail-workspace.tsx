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
import type { EtfMarketProduct, MemoCitation, MemoConfidence, MemoDecisionStatus, ReportDetailLoadState, ReportMemoDetail, ReportVersionComparison, ReportVersionSummary } from "@/lib/report-detail";
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

function CitationPanel({ citations, report, refreshing, refreshStatus, refreshError, onRefresh }: {
  citations: MemoCitation[]; report: ReportMemoDetail; refreshing: boolean;
  refreshStatus: string; refreshError: string; onRefresh: () => void;
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
          <Button size="sm" variant="ghost" className="text-paper hover:bg-paper/10 hover:text-paper" disabled={refreshing} onClick={onRefresh}><RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />{refreshing ? "刷新中" : "刷新"}</Button>
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
              <div className="text-right"><p className={cn("font-semibold", (product.returns?.["1m"] ?? 0) > 0 ? "text-[#8FD5C7]" : (product.returns?.["1m"] ?? 0) < 0 ? "text-red-300" : "text-paper/75")}>{formatPercent(product.returns?.["1m"])}</p><p className="mt-0.5 text-[9px] text-paper/45">{!availableMarketProduct(product) ? "行情未返回" : product.activity_trend === "higher" ? "活跃度升温" : product.activity_trend === "lower" ? "活跃度降温" : "活跃度平稳"}</p></div>
            </div>;
          })}</div> : <p className="mt-4 text-xs leading-5 text-paper/55">暂无成功行情快照。手动刷新后会在此显示，且不会改变报告版本。</p>}
          {refreshStatus && <p className="mt-3 rounded-lg bg-paper/[0.07] px-3 py-2 text-[10px] text-paper/65">{refreshStatus}</p>}
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

function availableMarketProduct(product: EtfMarketProduct) {
  return product.data_status === "available" || product.data_status === "partial" || product.data_status === "stale";
}

function EtfMarketTable({ products }: { products?: EtfMarketProduct[] }) {
  if (!products?.length) return <div className="mt-6 rounded-xl border border-dashed border-line p-7 text-center text-sm text-muted">尚无 ETF 行情行。点击右侧“刷新”后，这里会显示每只产品的成功值或明确失败状态。</div>;
  return (
    <div className="mt-6 overflow-x-auto rounded-xl border border-line bg-paper">
      <table className="w-full min-w-[820px] border-collapse text-left text-xs">
        <thead className="bg-ink/[0.035] text-[10px] uppercase tracking-[0.1em] text-muted"><tr><th className="px-4 py-3">ETF</th><th className="px-4 py-3">最新收盘</th><th className="px-4 py-3">1 月</th><th className="px-4 py-3">3 月波动</th><th className="px-4 py-3">最大回撤</th><th className="px-4 py-3">20 日平均成交额</th><th className="px-4 py-3">核验状态</th><th className="px-4 py-3">来源</th></tr></thead>
        <tbody className="divide-y divide-line">
          {products.slice(0, 6).map((product) => {
            const available = availableMarketProduct(product);
            return <tr key={product.ticker} className="align-top">
              <td className="px-4 py-3"><p className="font-mono font-semibold text-ink">{product.ticker}</p><p className="mt-1 max-w-36 text-[10px] text-muted">{product.issuer || product.category || "发行人待核验"}</p></td>
              <td className="px-4 py-3 font-semibold text-ink">{available ? formatMoney(product.last_close, product.currency) : "—"}</td>
              <td className="px-4 py-3 text-ink">{available ? formatPercent(product.returns?.["1m"]) : "—"}</td>
              <td className="px-4 py-3 text-ink">{available ? formatPercent(product.annualized_volatility_3m) : "—"}</td>
              <td className="px-4 py-3 text-ink">{available ? formatPercent(product.max_drawdown_3m) : "—"}</td>
              <td className="px-4 py-3 text-ink">{available ? formatMoney(product.average_dollar_volume_20d, product.currency) : "—"}</td>
              <td className="max-w-52 px-4 py-3"><span className={cn("font-semibold", available ? "text-signal" : "text-amber")}>{product.data_status === "stale" ? "缓存行情" : available ? "行情可用" : "未取得行情"}</span><p className="mt-1 text-[10px] leading-4 text-muted">{product.cross_source_validation?.status === "consistent" ? "双源可比字段一致" : product.cross_source_validation?.status === "conflict" ? "双源字段存在冲突" : product.cross_source_validation?.status === "single_source" ? "当前仅单源可用" : "字段口径不可直接比较"}</p>{product.error && <p title={product.error} className="mt-1 line-clamp-2 text-[10px] leading-4 text-muted">{product.error}</p>}</td>
              <td className="px-4 py-3"><div className="flex flex-wrap gap-1">{(product.sources ?? ["yfinance"]).map((source) => <Badge key={source}>{source === "tiantian" ? "天天基金" : source}</Badge>)}</div><div className="mt-2"><SourceButton url={product.source_url} publisher={product.ticker} /></div></td>
            </tr>;
          })}
        </tbody>
      </table>
    </div>
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

function normalizeStructuredItems(items?: Array<string | Record<string, unknown>>) {
  return (items ?? []).map((item) => {
    if (typeof item === "string") return item;
    return [item.driver, item.risk, item.mechanism, item.transmission, item.rationale].filter(Boolean).join("：");
  }).filter(Boolean) as string[];
}

function Stars({ value }: { value: number | null }) {
  if (value === null) return <span className="text-xs text-muted">未评估</span>;
  return <span className="tracking-[.12em] text-amber" aria-label={`${value} 星`}>{"★".repeat(value)}<span className="text-line">{"★".repeat(Math.max(0, 5 - value))}</span></span>;
}

export function ReportDetailWorkspace({ reportId }: { reportId: string }) {
  const [state, setState] = useState<ReportDetailLoadState>("idle");
  const [report, setReport] = useState<ReportMemoDetail | null>(null);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [versions, setVersions] = useState<ReportVersionSummary[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<number | undefined>(undefined);
  const [versionDiff, setVersionDiff] = useState<ReportVersionComparison | null>(null);
  const [marketRefreshing, setMarketRefreshing] = useState(false);
  const [marketRefreshStatus, setMarketRefreshStatus] = useState("");
  const [marketRefreshError, setMarketRefreshError] = useState("");

  const load = useCallback(() => {
    setState((current) => current === "ready" ? "refreshing" : "loading");
    setError("");
    reportDetailGateway.getReportDetail(reportId, selectedVersion)
      .then((value) => { setReport(value); setState("ready"); })
      .catch((reason: Error & { status?: number }) => {
        setError(reason.message || "报告读取失败。");
        setState(reason.status === 404 ? "not_found" : "failed");
      });
  }, [reportId, selectedVersion]);

  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => {
    void reportDetailGateway.getTimeline(reportId).then((payload) => setVersions(payload.versions)).catch(()=>setVersions([]));
  },[reportId,refreshKey]);
  async function compareLatestVersions(){
    if(versions.length<2)return;
    try { setVersionDiff(await reportDetailGateway.compareVersions(reportId, versions[1].version, versions[0].version)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "版本比较失败"); }
  }
  async function refreshMarketSnapshot() {
    setMarketRefreshing(true); setMarketRefreshStatus("行情刷新任务正在排队"); setMarketRefreshError("");
    try {
      const { runId } = await reportDetailGateway.refreshMarketSnapshot(reportId);
      for (let attempt = 0; attempt < 120; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const response = await fetch(`/api/research-runs/${encodeURIComponent(runId)}`);
        if (!response.ok) throw new Error(`刷新任务返回 ${response.status}`);
        const run = await response.json() as { status: string; progress?: number; error?: string };
        setMarketRefreshStatus(run.status === "queued" ? "行情刷新任务正在排队" : `正在逐只读取公开行情 · ${run.progress ?? 0}%`);
        if (run.status === "completed") { setMarketRefreshStatus("行情快照已更新"); setRefreshKey((value) => value + 1); return; }
        if (["failed", "cancelled", "blocked_configuration"].includes(run.status)) throw new Error(run.error || "市场快照刷新失败");
      }
      throw new Error("市场快照刷新超时，请稍后重新加载报告。");
    } catch (reason) {
      setMarketRefreshStatus("行情刷新未完成");
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
          <Button variant="outline" asChild><Link href="/theme-radar"><ArrowLeft className="h-4 w-4" />返回主题雷达</Link></Button>
          <Button onClick={() => setRefreshKey((value) => value + 1)}><RefreshCw className="h-4 w-4" />重新加载</Button>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("mx-auto max-w-[1480px] px-5 py-8 sm:px-8 sm:py-12 xl:px-12", state === "refreshing" && "opacity-70 transition")}>
      <nav className="flex items-center justify-between">
        <Link href="/theme-radar" className="inline-flex items-center gap-2 text-xs font-semibold text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" />返回主题雷达</Link>
        <Button variant="ghost" size="sm" onClick={() => { setSelectedVersion(undefined); setRefreshKey((value) => value + 1); }} disabled={state === "refreshing"}>
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
        <div className="mt-4 flex flex-wrap gap-2">{versions.map((version)=><button type="button" key={version.version} onClick={() => setSelectedVersion(version.version)} className={cn("rounded-full border px-3 py-1.5 text-[11px] font-semibold transition", report.version === version.version ? "border-signal bg-signal/[.08] text-signal" : "border-line text-muted hover:border-ink/20 hover:text-ink")}>V{version.version} · {version.content_hash.slice(0,8)}</button>)}{versions.length===0&&<p className="text-xs text-muted">当前报告尚无版本快照。</p>}</div>
        {versions.length > 0 && <ol className="mt-5 border-l border-line pl-5">{versions.slice(0, 4).map((version) => <li key={`timeline-${version.version}`} className="relative pb-4 last:pb-0"><span className="absolute -left-[24px] top-1 h-2 w-2 rounded-full border-2 border-signal bg-paper" /><div className="flex flex-wrap items-center gap-2"><button type="button" onClick={() => setSelectedVersion(version.version)} className="text-xs font-semibold text-ink hover:text-signal">V{version.version} · {formatDate(version.created_at)}</button>{version.change_tags?.map((tag) => <Badge key={tag}>{tag}</Badge>)}</div>{version.conclusion && <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{version.conclusion}</p>}</li>)}</ol>}
        {versionDiff&&<div className="mt-4 rounded-xl border border-line bg-canvas p-4 text-xs"><div className="grid gap-4 md:grid-cols-2"><div><p className="font-semibold text-ink">结论变化</p><p className="mt-2 leading-5 text-muted">{versionDiff.structured.conclusion.changed ? versionDiff.structured.conclusion.after : "两个版本的核心结论未发生变化。"}</p></div><div><p className="font-semibold text-ink">结构变化</p><p className="mt-2 leading-5 text-muted">评分变化 {versionDiff.structured.score_changes.length} 项 · ETF 新增 {versionDiff.structured.etfs_added.length} 只 · 关闭证据缺口 {versionDiff.structured.evidence_gaps_closed.length} 项</p></div></div><details className="mt-3 border-t border-line pt-3"><summary className="cursor-pointer text-muted">查看正文行级差异</summary><div className="mt-3 grid gap-4 md:grid-cols-2"><div>{versionDiff.added.slice(0,5).map((line,index)=><p key={index} className="mt-1 line-clamp-2 text-muted">+ {line}</p>)}</div><div>{versionDiff.removed.slice(0,5).map((line,index)=><p key={index} className="mt-1 line-clamp-2 text-muted">− {line}</p>)}</div></div></details></div>}
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

          {report.structuredAnalysis && <>
            <section className="mt-12">
              <div className="flex items-center gap-3 border-b border-ink pb-4"><span className="font-mono text-xs text-signal">02</span><div><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-muted">Industry structure</p><h2 className="mt-1 text-2xl font-semibold tracking-[-.03em] text-ink">为什么选择与产业链潜力</h2></div></div>
              <div className="mt-6 grid gap-5 lg:grid-cols-[.8fr_1.2fr]"><div className="rounded-2xl bg-ink p-6 text-paper"><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-[#8FD5C7]">Selection reason</p><p className="mt-4 text-base leading-8 text-paper/85">{report.structuredAnalysis.whyTheme?.selection_reason || report.investmentThesis}</p>{report.structuredAnalysis.industryChain?.priority_logic && <p className="mt-5 border-t border-paper/10 pt-4 text-xs leading-6 text-paper/60">{report.structuredAnalysis.industryChain.priority_logic}</p>}</div><div className="grid gap-3 sm:grid-cols-2">{(report.structuredAnalysis.industryChain?.segments ?? []).map((segment, index) => <article key={`${segment.name}-${index}`} className="rounded-2xl border border-line bg-paper p-5"><div className="flex items-center justify-between gap-3"><h3 className="font-semibold text-ink">{segment.name || `产业环节 ${index + 1}`}</h3><Badge>{segment.potential || "待评估"}</Badge></div><p className="mt-3 text-sm leading-6 text-muted">{segment.rationale || "尚缺少足够证据判断该环节的潜力。"}</p>{segment.pricing_power && <p className="mt-3 border-t border-line pt-3 text-xs leading-5 text-ink/70">定价权：{segment.pricing_power}</p>}</article>)}{!(report.structuredAnalysis.industryChain?.segments?.length) && <div className="col-span-full rounded-2xl border border-dashed border-line p-8 text-center text-sm text-muted">产业链环节尚未形成可审计排序。</div>}</div></div>
            </section>

            <section className="mt-12 rounded-2xl border border-line bg-paper p-6 shadow-card sm:p-8"><div className="flex items-center gap-3"><span className="font-mono text-xs text-signal">03</span><h2 className="text-xl font-semibold text-ink">增长驱动力与风险传导</h2></div><div className="mt-7 grid gap-8 lg:grid-cols-2"><DataColumn eyebrow="Growth drivers" title="增长驱动力" items={normalizeStructuredItems(report.structuredAnalysis.growthDrivers)} empty="尚未形成可验证的增长驱动链条。" /><DataColumn eyebrow="Risk transmission" title="风险与反向指标" items={normalizeStructuredItems(report.structuredAnalysis.risks)} empty="尚未形成结构化风险传导路径。" /></div></section>

            <section className="mt-12"><div className="flex items-center justify-between border-b border-line pb-4"><div><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-signal">5–10 year outlook</p><h2 className="mt-1 text-2xl font-semibold tracking-[-.03em] text-ink">长期三情景</h2></div><Badge>非收益预测</Badge></div><div className="mt-6 grid gap-4 lg:grid-cols-3">{(report.structuredAnalysis.scenarios ?? []).map((scenario) => <article key={scenario.id} className={cn("rounded-2xl border p-5", scenario.id === "optimistic" ? "border-signal/25 bg-signal/[.045]" : scenario.id === "pessimistic" ? "border-amber/25 bg-amber/[.045]" : "border-line bg-paper")}><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-muted">{scenario.id}</p><h3 className="mt-2 text-lg font-semibold text-ink">{scenario.label}</h3><p className="mt-4 text-sm leading-6 text-muted">{scenario.industry_path}</p><p className="mt-4 border-t border-line pt-4 text-xs leading-5 text-ink/75"><strong>ETF 角度：</strong>{scenario.etf_implication}</p></article>)}</div></section>

            <section className="mt-12 overflow-hidden rounded-2xl border border-line bg-paper shadow-card"><header className="border-b border-line bg-ink px-6 py-5 text-paper"><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-[#8FD5C7]">Integrated judgment</p><h2 className="mt-1 text-xl font-semibold">综合判断</h2></header><div className="divide-y divide-line">{(report.structuredAnalysis.scorecard ?? []).map((item) => <div key={item.id} className="grid gap-2 px-6 py-4 sm:grid-cols-[minmax(0,220px)_110px_minmax(0,1fr)] sm:items-center"><p className="text-sm font-semibold text-ink">{item.label}</p><Stars value={item.stars} /><p className="text-xs leading-5 text-muted">{item.reason}</p></div>)}</div><div className="border-t border-line bg-canvas px-6 py-5"><p className="text-base font-semibold leading-7 text-ink">{report.conclusion.statement}</p></div></section>

            {(report.structuredAnalysis.evidenceGaps?.length ?? report.conclusion.evidenceGaps?.length ?? 0) > 0 && <section className="mt-12 rounded-2xl border border-amber/25 bg-[#F7F5F0] p-6 sm:p-8"><div className="flex items-center gap-3"><TriangleAlert className="h-5 w-5 text-amber" /><div><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-amber">Evidence gaps</p><h2 className="mt-1 text-xl font-semibold text-ink">证据不足在哪里，以及为什么影响判断</h2></div></div><div className="mt-6 space-y-4">{(report.structuredAnalysis.evidenceGaps ?? report.conclusion.evidenceGaps ?? []).map((gap, index) => <article key={`${gap.area}-${index}`} className="rounded-xl border border-line bg-paper p-5"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold text-ink">{gap.area}</h3><Badge>{gap.status || "待补证"}</Badge></div><dl className="mt-4 grid gap-3 text-xs leading-5 sm:grid-cols-2"><div><dt className="font-semibold text-muted">缺少什么</dt><dd className="mt-1 text-ink/80">{gap.gap}</dd></div><div><dt className="font-semibold text-muted">为何缺少</dt><dd className="mt-1 text-ink/80">{gap.why_missing}</dd></div><div><dt className="font-semibold text-muted">对结论的影响</dt><dd className="mt-1 text-ink/80">{gap.impact}</dd></div><div><dt className="font-semibold text-muted">补证路径</dt><dd className="mt-1 text-ink/80">{gap.next_action}</dd></div></dl></article>)}</div></section>}
          </>}

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
            <div className="mt-8 border-t border-line pt-6">
              <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-signal">Market snapshot ledger</p><h3 className="mt-1 text-base font-semibold text-ink">ETF 行情与交易活跃度</h3></div><p className="text-[10px] text-muted">独立快照 · 不改变报告版本 · 最多展示 6 只</p></div>
              <EtfMarketTable products={report.latestMarketSnapshot?.products ?? report.etfLandscape.products} />
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
        <CitationPanel citations={citations} report={report} refreshing={marketRefreshing} refreshStatus={marketRefreshStatus} refreshError={marketRefreshError} onRefresh={() => void refreshMarketSnapshot()} />
      </div>
    </div>
  );
}
