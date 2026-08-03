"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/metric-card";
import { ThemeCard } from "@/components/theme-card";
import { ResearchTaskCard } from "@/components/research-task-card";
import { PageHeader } from "@/components/page-header";
import { SourceIntelligenceWall } from "@/components/source-intelligence-wall";

type Dashboard = {
  metrics:{themes:number;evidence:number;runs:number;reports:number};
  themes:Array<{slug:string;title:string;stage:string;metrics:{themeScore:number};evidenceCount:number;sourceTypeCount:number;description:string}>;
  runs:Array<{run_id:string;request:{topic?:string};status:string;stage:string;progress:number;updated_at:string}>;
};

export function DashboardWorkspace(){
  const [data,setData]=useState<Dashboard|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{fetch("/api/dashboard").then((response)=>{if(!response.ok)throw new Error(`首页接口返回 ${response.status}`);return response.json();}).then(setData).catch((reason)=>setError(reason instanceof Error?reason.message:"首页读取失败"));},[]);
  const metrics=data?[{label:"观察主题",value:String(data.metrics.themes),detail:"治理后主题",trend:"真实数据"},{label:"有效证据",value:String(data.metrics.evidence),detail:"已分配证据",trend:"可追溯"},{label:"研究任务",value:String(data.metrics.runs),detail:"历史与当前任务",trend:"持久化"},{label:"研究报告",value:String(data.metrics.reports),detail:"资料库资产",trend:"已审计"}]:[];
  return <div className="mx-auto max-w-[1500px] px-5 py-10 sm:px-8 sm:py-14 xl:px-12">
    <PageHeader index="01" eyebrow="Dashboard" title="把公开信息，变成可验证的主题判断。" description="聚合监管文件、论文、专利、公司行动与市场讨论，帮助研究团队识别变化、核验证据，并沉淀为可复用的研究资产。" actions={<><Button variant="outline" asChild><Link href="/evidence">查看今日证据</Link></Button><Button asChild><Link href="/research"><Plus className="h-4 w-4" />新建研究</Link></Button></>} />
    {error&&<div className="mt-8 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">{error}</div>}
    <section className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{metrics.map((metric)=><MetricCard key={metric.label}{...metric}/>)}</section>
    <SourceIntelligenceWall/>
    <section className="mt-14"><div className="mb-6 flex items-end justify-between gap-4"><div><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-signal">Theme signals</p><h2 className="mt-2 text-2xl font-semibold text-ink">正在形成的主题信号</h2></div><Button variant="ghost" asChild><Link href="/theme-radar">进入主题雷达 <ArrowRight className="h-4 w-4" /></Link></Button></div><div className="grid gap-4 xl:grid-cols-3">{(data?.themes??[]).map((theme)=><ThemeCard key={theme.slug} title={theme.title} status={theme.stage==="deep_research"?"重点研究":"持续观察"} score={theme.metrics.themeScore} evidence={theme.evidenceCount} change="历史不足" sources={theme.sourceTypeCount} summary={theme.description}/>)}</div></section>
    <section className="mt-14 pb-10"><div className="mb-6"><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-signal">Research queue</p><h2 className="mt-2 text-2xl font-semibold text-ink">研究工作流</h2></div><div className="grid gap-4 lg:grid-cols-3">{(data?.runs??[]).map((run)=><ResearchTaskCard key={run.run_id} title={run.request?.topic||run.run_id} theme={run.status} stage={run.stage} progress={run.progress} owner="本地研究工作流" updated={run.updated_at}/>)}</div></section>
  </div>;
}
