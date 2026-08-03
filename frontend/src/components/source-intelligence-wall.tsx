"use client";
import { useEffect, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { SourceLogoCard, type SourceState } from "@/components/source-logo-card";

type SourceCapability = { source_name:string; short_name:string; display_name:string; category:string; logo_url?:string|null; status:string; coverage_note:string };

export function SourceIntelligenceWall() {
  const [sources,setSources]=useState<Array<{name:string;label:string;logo?:string|null;state:SourceState;freshness:string}>>([]);
  const [coverage,setCoverage]=useState("—/—");
  useEffect(()=>{ fetch("/api/capabilities").then((response)=>response.json()).then((payload:{sources?:SourceCapability[];source_coverage?:{label:string}})=>{ const items=payload.sources??[]; setCoverage(payload.source_coverage?.label??`${items.filter((item)=>item.status==="healthy").length}/${items.length}`); setSources(items.map((item)=>({name:item.short_name||item.display_name,label:item.category,logo:item.logo_url,state:item.status==="healthy"?"正常":item.status==="degraded"?"降级":"已关闭",freshness:item.coverage_note}))); }).catch(()=>setSources([])); },[]);
  return (
    <section className="mt-14">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-signal">信息源状态</p><h2 className="mt-2 text-2xl font-semibold tracking-[-0.035em] text-ink">连接全球公开投资信息</h2></div>
        <button className="flex items-center gap-2 text-sm font-semibold text-ink hover:text-signal">数据覆盖 {coverage} <ArrowUpRight className="h-4 w-4" /></button>
      </div>
      <div className="relative -mx-4 overflow-x-auto px-4 pb-3 sm:mx-0 sm:px-0">
        <div className="absolute left-5 right-5 top-[31px] h-px bg-line" aria-hidden="true" />
        <div className="relative flex min-w-max gap-3">{sources.map((source) => <SourceLogoCard key={source.name} {...source} />)}</div>
      </div>
    </section>
  );
}
