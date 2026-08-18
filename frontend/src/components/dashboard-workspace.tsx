"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, Filter, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/metric-card";
import { ResearchTaskCard } from "@/components/research-task-card";
import { PageHeader } from "@/components/page-header";
import { SourceIntelligenceWall } from "@/components/source-intelligence-wall";

type Facet = { value:string; count:number };
type BriefEvent = { evidence_id:string; title:string; summary:string; occurred_at:string; theme:string; source:string; industry_chain:string };
type Dashboard = {
  briefing:{briefing_id:string|null;as_of_date:string|null;generated_at:string|null;status:"available"|"not_available"};
  metrics:{themes:number;evidence:number;runs:number;reports:number}; events:BriefEvent[];
  facets:{themes:Facet[];industry_chains:Facet[];sources:Facet[]};
  exceptions:{quality_statuses:Record<string,number>;source_health:Array<{source:string;status:string;coverage_note:string}>};
  runs:Array<{run_id:string;request:{topic?:string};status:string;stage:string;progress:number;updated_at:string}>;
};
type Filters = { theme:string; industry_chain:string; source:string };
const emptyFilters:Filters={theme:"",industry_chain:"",source:""};

function Drilldown({label,value,items,onChange}:{label:string;value:string;items:Facet[];onChange:(value:string)=>void}){
  return <label className="min-w-[150px] flex-1"><span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[.14em] text-muted">{label}</span><select value={value} onChange={(event)=>onChange(event.target.value)} className="h-10 w-full rounded-lg border border-line bg-paper px-3 text-sm text-ink outline-none focus:border-signal"><option value="">全部</option>{items.map((item)=><option key={item.value} value={item.value}>{item.value} · {item.count}</option>)}</select></label>;
}

export function DashboardWorkspace(){
  const [data,setData]=useState<Dashboard|null>(null); const [error,setError]=useState(""); const [filters,setFilters]=useState<Filters>(emptyFilters);
  useEffect(()=>{const controller=new AbortController(); const params=new URLSearchParams(Object.entries(filters).filter(([,value])=>value)); fetch(`/api/dashboard?${params}`,{signal:controller.signal}).then((response)=>{if(!response.ok)throw new Error(`首页接口返回 ${response.status}`);return response.json();}).then(setData).catch((reason)=>{if((reason as Error).name!=="AbortError")setError(reason instanceof Error?reason.message:"首页读取失败");});return()=>controller.abort();},[filters]);
  const metrics=useMemo(()=>data?[{label:"观察主题",value:String(data.metrics.themes),detail:"治理后主题",trend:"真实数据"},{label:"本次证据",value:String(data.metrics.evidence),detail:"当前下钻结果",trend:"冻结快照"},{label:"研究任务",value:String(data.metrics.runs),detail:"历史与当前任务",trend:"持久化"},{label:"研究报告",value:String(data.metrics.reports),detail:"资料库资产",trend:"已审计"}]:[],[data]);
  const exceptionCount=Object.values(data?.exceptions.quality_statuses??{}).reduce((sum,value)=>sum+value,0)+((data?.exceptions.source_health.length??0));
  return <div className="mx-auto max-w-[1500px] px-5 py-10 sm:px-8 sm:py-14 xl:px-12">
    <PageHeader index="今日" eyebrow="Daily briefing" title={data?.briefing.status==="available"?`${data.briefing.as_of_date} 的已治理信息`:"等待第一份每日简报"} description="只展示通过完整性门、已冻结到每日快照的公开事实；下钻不会重新采集或改变快照。" actions={<><Button variant="outline" asChild><Link href="/theme-radar">主题雷达</Link></Button><Button asChild><Link href="/research"><Plus className="h-4 w-4" />新建研究</Link></Button></>} />
    {error&&<div className="mt-8 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">{error}</div>}
    <section className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{metrics.map((metric)=><MetricCard key={metric.label}{...metric}/>)}</section>
    <section className="mt-8 rounded-2xl border border-line bg-paper p-5 shadow-card"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.16em] text-signal"><Filter className="h-3.5 w-3.5"/>按事实下钻</p><p className="mt-1 text-sm text-muted">主题、产业链位置和来源会同时生效。</p></div><Button variant="ghost" size="sm" onClick={()=>setFilters(emptyFilters)}>清除筛选</Button></div><div className="mt-4 flex flex-wrap gap-3"><Drilldown label="主题" value={filters.theme} items={data?.facets.themes??[]} onChange={(theme)=>setFilters((value)=>({...value,theme}))}/><Drilldown label="产业链" value={filters.industry_chain} items={data?.facets.industry_chains??[]} onChange={(industry_chain)=>setFilters((value)=>({...value,industry_chain}))}/><Drilldown label="来源" value={filters.source} items={data?.facets.sources??[]} onChange={(source)=>setFilters((value)=>({...value,source}))}/></div></section>
    <section className="mt-8 grid gap-4 xl:grid-cols-[1fr_310px]"><div className="rounded-2xl border border-line bg-paper shadow-card"><div className="border-b border-line px-5 py-4"><p className="text-[10px] font-semibold uppercase tracking-[.16em] text-signal">Briefing facts</p><h2 className="mt-1 text-xl font-semibold text-ink">发生了什么</h2></div><div className="divide-y divide-line">{data?.events.map((event)=><article key={event.evidence_id} className="px-5 py-5"><div className="flex flex-wrap gap-2 text-[10px] font-semibold text-muted"><span>{event.occurred_at}</span><span>·</span><span>{event.theme}</span><span>·</span><span>{event.industry_chain}</span><span>·</span><span>{event.source}</span></div><h3 className="mt-2 text-base font-semibold text-ink">{event.title}</h3><p className="mt-2 text-sm leading-6 text-muted">{event.summary}</p></article>)}{data?.briefing.status==="not_available"&&<div className="px-5 py-14 text-center text-sm text-muted">完成每日同步后，这里会显示第一份冻结简报。</div>}{data?.briefing.status==="available"&&!data.events.length&&<div className="px-5 py-14 text-center text-sm text-muted">没有符合当前下钻条件的已治理信息。</div>}</div></div><aside className="rounded-2xl border border-line bg-paper p-5"><div className="flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-amber"/><h2 className="font-semibold text-ink">采集异常</h2></div><p className="mt-2 text-sm text-muted">{exceptionCount?`共 ${exceptionCount} 项等待处理。`:"当前没有聚合异常。"}</p><div className="mt-4 space-y-2">{Object.entries(data?.exceptions.quality_statuses??{}).map(([status,count])=><div key={status} className="flex justify-between rounded-lg bg-canvas px-3 py-2 text-xs"><span>{status}</span><strong>{count}</strong></div>)}{data?.exceptions.source_health.map((item)=><div key={item.source} className="rounded-lg bg-amber/10 px-3 py-2 text-xs text-ink"><strong>{item.source} · {item.status}</strong><p className="mt-1 text-muted">{item.coverage_note}</p></div>)}</div></aside></section>
    <SourceIntelligenceWall/>
    <section className="mt-14 pb-10"><div className="mb-6 flex items-end justify-between gap-4"><div><p className="text-[11px] font-semibold uppercase tracking-[.16em] text-signal">Research queue</p><h2 className="mt-2 text-2xl font-semibold text-ink">研究工作流</h2></div><Button variant="ghost" asChild><Link href="/research">进入工作台 <ArrowRight className="h-4 w-4"/></Link></Button></div><div className="grid gap-4 lg:grid-cols-3">{(data?.runs??[]).map((run)=><ResearchTaskCard key={run.run_id} title={run.request?.topic||run.run_id} theme={run.status} stage={run.stage} progress={run.progress} owner="本地研究工作流" updated={run.updated_at}/>)}</div></section>
  </div>;
}
