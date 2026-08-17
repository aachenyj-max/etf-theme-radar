"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, CalendarClock, Database, LoaderCircle, RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Category = "sp500" | "exchange" | "active";
type SortKey = "code" | "name" | "operating_fee" | "scale_billion" | "return_2025" | "rolling_1y" | "yesterday_return" | "tracking_error" | "premium_rate" | "average_turnover_billion_20d";
type EtfItem = {
  code: string; name: string; c_code?: string; operating_fee?: number | null; scale_billion?: number | null;
  scale_date?: string; return_2025?: number | null; rolling_1y?: number | null; yesterday_return?: number | null;
  tracking_error?: number | null; tracking_error_date?: string; daily_limit_yuan?: number | string | null;
  purchase_status?: string; tracking_index?: string; premium_rate?: number | null;
  average_turnover_billion_20d?: number | null; turnover_as_of?: string; source_url?: string;
};
type PreviewResponse = {
  state: "ready" | "degraded" | "empty"; source: string; source_homepage?: string; market_as_of?: string;
  collected_at?: string; counts: Record<Category, number>; items: EtfItem[]; filtered_count: number;
  total?: number; errors?: Array<{ code?: string; field?: string; error: string }>;
};

const categories: Array<{ id: Category; label: string; note: string }> = [
  { id: "sp500", label: "标普 500", note: "场外指数与联接基金" },
  { id: "exchange", label: "场内 ETF", note: "美股相关交易型基金" },
  { id: "active", label: "美股主动", note: "主动权益 QDII" },
];

const dash = "—";
const number = (value: number | null | undefined, digits = 2) => value == null ? dash : value.toFixed(digits);
const percent = (value: number | null | undefined, digits = 2) => value == null ? dash : `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
const moneyLimit = (value: EtfItem["daily_limit_yuan"]) => {
  if (value == null || value === "") return dash;
  if (typeof value === "string") return value;
  if (value >= 100_000_000) return `${number(value / 100_000_000)} 亿`;
  if (value >= 10_000) return `${number(value / 10_000)} 万`;
  return `${number(value, 0)} 元`;
};
const returnTone = (value?: number | null) => value == null ? "text-muted" : value > 0 ? "text-[#B84A46]" : value < 0 ? "text-[#2D806C]" : "text-ink";
const premiumTone = (value?: number | null) => value == null || value <= 1 ? "text-ink" : value > 3 ? "bg-[#B84A46]/10 text-[#A23B37]" : value > 2 ? "bg-orange-100 text-orange-700" : "bg-amber/10 text-amber";

function Metric({ value, kind = "return" }: { value?: number | null; kind?: "return" | "plain" }) {
  return <span className={cn("tabular-nums", kind === "return" && returnTone(value))}>{kind === "return" ? percent(value) : number(value)}</span>;
}

function SortLabel({ label, field, active, order, onSort }: { label: string; field: SortKey; active: SortKey; order: "asc" | "desc"; onSort: (field: SortKey) => void }) {
  const Icon = order === "desc" ? ArrowDown : ArrowUp;
  return <button type="button" onClick={() => onSort(field)} className="inline-flex items-center gap-0.5 text-left transition hover:text-ink">{label}{active === field && <Icon className="h-3 w-3 text-signal" />}</button>;
}

export function EtfPreviewWorkspace() {
  const [view, setView] = useState<"products" | "sec" | "holdings">("products");
  const [category, setCategory] = useState<Category>("sp500");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("scale_billion");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [data, setData] = useState<PreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState("");

  useEffect(() => { const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 220); return () => window.clearTimeout(timer); }, [query]);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ category, sort_by: sortBy, order });
      if (debouncedQuery) params.set("q", debouncedQuery);
      const response = await fetch(`/api/etf-preview?${params}`, { headers: { Accept: "application/json" }, signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setData(await response.json() as PreviewResponse);
    } catch (reason) {
      if ((reason as Error).name !== "AbortError") setError("ETF 数据暂时无法读取，请稍后重试。");
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [category, debouncedQuery, order, sortBy]);

  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);

  const onSort = (field: SortKey) => { if (sortBy === field) setOrder((value) => value === "desc" ? "asc" : "desc"); else { setSortBy(field); setOrder("desc"); } };

  const refresh = async () => {
    setRefreshing(true); setRefreshNote("");
    try {
      const response = await fetch("/api/etf-preview/refresh", { method: "POST", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json() as { poll_url: string };
      setRefreshNote("已进入同步队列");
      for (let attempt = 0; attempt < 90; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const poll = await fetch(payload.poll_url, { headers: { Accept: "application/json" } });
        if (!poll.ok) continue;
        const state = await poll.json() as { status?: string };
        if (state.status === "completed") { setRefreshNote("行情已更新"); await load(); break; }
        if (["failed", "cancelled"].includes(state.status ?? "")) { setRefreshNote("本次同步失败，继续显示上次成功数据"); break; }
        setRefreshNote(state.status === "running" ? "正在抓取公开数据" : "正在等待同步");
      }
    } catch { setRefreshNote("刷新请求失败，未改动现有数据"); }
    finally { setRefreshing(false); }
  };

  const total = useMemo(() => data ? Object.values(data.counts).reduce((sum, value) => sum + value, 0) : 0, [data]);
  const asOf = data?.market_as_of || dash;

  return (
    <div className="min-w-0 px-5 py-7 xl:px-8 xl:py-9">
      <section className="border-b border-line pb-6">
        <div className="flex items-start justify-between gap-6">
          <div><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-signal">ETF universe / public data</p><h1 className="mt-2 text-[clamp(2rem,3.5vw,3.25rem)] font-semibold tracking-[-0.055em] text-ink">ETF 预览</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted">集中比较标普 500、场内 ETF 与美股主动基金。收益为历史数据，不构成投资建议。</p></div>
          <Button variant="outline" onClick={() => void refresh()} disabled={refreshing}><RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />{refreshing ? "同步中" : "刷新数据"}</Button>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-4">
          <div className="bg-paper px-4 py-3"><p className="flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-muted"><Database className="h-3.5 w-3.5" />数据来源</p><a href={data?.source_homepage || "https://1234567.com.cn/"} target="_blank" rel="noreferrer" className="mt-1 block text-sm font-semibold text-ink hover:text-signal">{data?.source || "天天基金网"}</a></div>
          <div className="bg-paper px-4 py-3"><p className="flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-muted"><CalendarClock className="h-3.5 w-3.5" />行情日期</p><p className="mt-1 text-sm font-semibold tabular-nums text-ink">{asOf}</p></div>
          <div className="bg-paper px-4 py-3"><p className="text-[10px] uppercase tracking-[0.12em] text-muted">基金总数</p><p className="mt-1 text-sm font-semibold tabular-nums text-ink">{data ? `${total} 只` : dash}</p></div>
          <div className="bg-paper px-4 py-3"><p className="text-[10px] uppercase tracking-[0.12em] text-muted">当前显示</p><p className="mt-1 text-sm font-semibold tabular-nums text-ink">{data ? `${data.filtered_count} 只` : dash}</p></div>
        </div>
      </section>

      <section className="mt-6">
        <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="ETF 研究分区">
          {([ ["products","产品预览"], ["sec","SEC 新 ETF"], ["holdings","持仓变化"] ] as const).map(([id,label]) => <button key={id} role="tab" aria-selected={view===id} onClick={() => setView(id)} className={cn("rounded-lg border px-3 py-2 text-xs font-semibold transition", view===id ? "border-ink bg-ink text-white" : "border-line bg-paper text-ink hover:border-ink/25")}>{label}</button>)}
        </div>
        {view !== "products" && <div className="mb-5 rounded-2xl border border-line bg-paper p-5 text-sm"><p className="font-semibold text-ink">{view === "sec" ? "SEC 新 ETF" : "发行人官方持仓变化"}</p><p className="mt-2 leading-6 text-muted">当前 ETF 预览快照的来源为 {data?.source || "尚未同步"}，截至日为 {asOf}。该快照没有可安全映射到此分区的独立记录，因此状态为 not_assessed；系统不会从产品名称、旧净值或未核验持仓推断新 ETF 或持仓变化。</p>{data?.errors?.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber">{data.errors.map((item,index)=><li key={`${item.code||"error"}-${index}`}>{item.code || "refresh_error"}：{item.error}</li>)}</ul> : <p className="mt-3 text-xs text-muted">刷新失败原因：无。</p>}</div>}
        {view === "products" && <>
        <div className="flex items-end justify-between gap-5">
          <div className="grid flex-1 grid-cols-3 gap-2" role="tablist" aria-label="ETF 分类">
            {categories.map((item) => <button key={item.id} role="tab" aria-selected={category === item.id} onClick={() => { setCategory(item.id); setSortBy("scale_billion"); setOrder("desc"); }} className={cn("rounded-xl border px-4 py-3 text-left transition", category === item.id ? "border-ink bg-ink text-white shadow-card" : "border-line bg-paper text-ink hover:border-ink/25")}><span className="flex items-center justify-between gap-2 text-sm font-semibold"><span>{item.label}</span><span className={cn("tabular-nums", category === item.id ? "text-white/75" : "text-muted")}>{data?.counts?.[item.id] ?? dash}</span></span><span className={cn("mt-1 block text-[10px]", category === item.id ? "text-white/60" : "text-muted")}>{item.note}</span></button>)}
          </div>
          <label className="flex h-[58px] w-[min(31vw,340px)] shrink-0 items-center gap-2 rounded-xl border border-line bg-paper px-4 focus-within:border-signal"><Search className="h-4 w-4 text-muted" /><input value={query} onChange={(event) => setQuery(event.target.value)} className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted/60" placeholder="搜索基金名称或代码" aria-label="搜索基金名称或代码" /></label>
        </div>
        {(refreshNote || data?.state === "degraded") && <div className="mt-3 flex items-center gap-2 text-xs text-amber"><AlertTriangle className="h-3.5 w-3.5" />{refreshNote || "部分字段暂未核验，继续显示最后一次成功快照。"}</div>}
        </>}
      </section>

      {view === "products" && <section className="mt-5 overflow-hidden rounded-2xl border border-line bg-paper shadow-card" aria-busy={loading}>
        {error ? <div className="grid min-h-64 place-items-center p-8 text-center"><div><AlertTriangle className="mx-auto h-6 w-6 text-amber" /><p className="mt-3 text-sm text-ink">{error}</p><Button className="mt-4" variant="outline" size="sm" onClick={() => void load()}>重新读取</Button></div></div> : loading && !data ? <div className="grid min-h-64 place-items-center"><LoaderCircle className="h-6 w-6 animate-spin text-signal" /></div> : <EtfTable category={category} data={data} sortBy={sortBy} order={order} onSort={onSort} />}
      </section>}
      {view === "products" && <p className="mt-3 text-[10px] leading-5 text-muted">运作费率 = 管理费 + 托管费（年化）；2025 涨幅按完整自然年度复权累计净值计算；“昨日”指最新净值日涨幅。规模和其他指标日期可悬停查看。</p>}
    </div>
  );
}

function EtfTable({ category, data, sortBy, order, onSort }: { category: Category; data: PreviewResponse | null; sortBy: SortKey; order: "asc" | "desc"; onSort: (field: SortKey) => void }) {
  const rows = data?.items ?? [];
  if (!rows.length) return <div className="grid min-h-56 place-items-center text-sm text-muted">没有匹配的基金</div>;
  const sortable = (label: string, field: SortKey) => <SortLabel label={label} field={field} active={sortBy} order={order} onSort={onSort} />;
  return <table className="w-full table-fixed border-collapse text-left text-[11px] leading-4 text-ink [&_td]:px-2 [&_td]:py-3 [&_th]:px-2 [&_th]:py-3 [&_th]:align-bottom">
    <colgroup>{category === "exchange" ? <><col className="w-[7%]"/><col className="w-[17%]"/><col className="w-[17%]"/><col className="w-[8%]"/><col className="w-[8%]"/><col className="w-[9%]"/><col className="w-[9%]"/><col className="w-[8%]"/><col className="w-[8%]"/><col className="w-[9%]"/></> : category === "sp500" ? <><col className="w-[7%]"/><col className="w-[18%]"/><col className="w-[7%]"/><col className="w-[7%]"/><col className="w-[7%]"/><col className="w-[8%]"/><col className="w-[8%]"/><col className="w-[8%]"/><col className="w-[8%]"/><col className="w-[11%]"/><col className="w-[11%]"/></> : <><col className="w-[8%]"/><col className="w-[24%]"/><col className="w-[8%]"/><col className="w-[8%]"/><col className="w-[8%]"/><col className="w-[9%]"/><col className="w-[9%]"/><col className="w-[9%]"/><col className="w-[10%]"/><col className="w-[7%]"/></>}</colgroup>
    <thead className="bg-[#F2F2EE] text-[10px] font-semibold text-muted"><tr>{category === "exchange" ? <><th>{sortable("代码", "code")}</th><th>{sortable("ETF 名称", "name")}</th><th>跟踪指数</th><th>{sortable("运作费率", "operating_fee")}</th><th>{sortable("规模（亿）", "scale_billion")}</th><th>{sortable("2025 涨幅", "return_2025")}</th><th>{sortable("近一年滚动", "rolling_1y")}</th><th>{sortable("昨日涨幅", "yesterday_return")}</th><th>{sortable("溢价率", "premium_rate")}</th><th>{sortable("日均成交（亿）", "average_turnover_billion_20d")}</th></> : <><th>{sortable("代码", "code")}</th><th>{sortable("基金名称", "name")}</th><th>C 类代码</th><th>{sortable("运作费率", "operating_fee")}</th><th>{sortable("规模（亿）", "scale_billion")}</th><th>{sortable("2025 涨幅", "return_2025")}</th><th>{sortable("近一年滚动", "rolling_1y")}</th><th>{sortable("昨日涨幅", "yesterday_return")}</th>{category === "sp500" && <th>{sortable("跟踪误差", "tracking_error")}</th>}<th>每日限额</th><th>申购状态</th></>}</tr></thead>
    <tbody>{rows.map((item) => <tr key={item.code} className="border-t border-line/80 transition hover:bg-ink/[0.018]">
      <td className="font-semibold tabular-nums"><a href={item.source_url} target="_blank" rel="noreferrer" className="hover:text-signal">{item.code}</a></td><td><span title={item.name} className="block truncate font-medium">{item.name}</span></td>
      {category === "exchange" ? <><td><span title={item.tracking_index} className="block truncate text-muted">{item.tracking_index || dash}</span></td><td>{number(item.operating_fee)}%</td><td title={item.scale_date}>{number(item.scale_billion)}</td><td><Metric value={item.return_2025}/></td><td><Metric value={item.rolling_1y}/></td><td><Metric value={item.yesterday_return}/></td><td><span className={cn("inline-flex rounded-md px-1.5 py-0.5 tabular-nums", premiumTone(item.premium_rate))}>{percent(item.premium_rate)}</span></td><td title={item.turnover_as_of}>{number(item.average_turnover_billion_20d)}</td></> : <><td className="tabular-nums text-muted">{item.c_code || dash}</td><td>{number(item.operating_fee)}%</td><td title={item.scale_date}>{number(item.scale_billion)}</td><td><Metric value={item.return_2025}/></td><td><Metric value={item.rolling_1y}/></td><td><Metric value={item.yesterday_return}/></td>{category === "sp500" && <td title={item.tracking_error_date}>{item.tracking_error == null ? dash : `${number(item.tracking_error)}%`}</td>}<td>{moneyLimit(item.daily_limit_yuan)}</td><td><span className={cn("inline-flex rounded-md px-1.5 py-0.5", item.purchase_status?.includes("暂停") ? "bg-amber/10 text-amber" : "bg-signal/[0.08] text-signal")}>{item.purchase_status || dash}</span></td></>}
    </tr>)}</tbody>
  </table>;
}
