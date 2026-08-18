"use client";

import * as Dialog from "@radix-ui/react-dialog";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { BarChart3, FolderSearch2, Home, LibraryBig, Menu, Search, Settings, TableProperties, X } from "lucide-react";
import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { InternalAuthGate } from "@/components/internal-auth-gate";

const navigation = [
  { href: "/", label: "首页", icon: Home },
  { href: "/theme-radar", label: "主题雷达", icon: BarChart3 },
  { href: "/etf-preview", label: "ETF 预览", icon: TableProperties },
  { href: "/research", label: "研究工作台", icon: FolderSearch2 },
  { href: "/knowledge", label: "个人知识库", icon: LibraryBig }
];

type ConnectorCapability = { enabled: boolean; status: string; checked_at?: string };

function DataCoverage() {
  const [connectors, setConnectors] = useState<ConnectorCapability[] | null>(null);
  useEffect(() => {
    let active = true;
    void fetch("/api/capabilities", { headers: { Accept: "application/json" } })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(String(response.status))))
      .then((payload: { connectors?: ConnectorCapability[] }) => { if (active) setConnectors(payload.connectors ?? []); })
      .catch(() => { if (active) setConnectors([]); });
    return () => { active = false; };
  }, []);
  const healthy = connectors?.filter((item) => item.enabled && item.status === "healthy").length ?? 0;
  const total = connectors?.length ?? 0;
  const unavailable = Math.max(0, total - healthy);
  const fullyReady = total > 0 && unavailable === 0;
  return (
    <div className="rounded-2xl border border-line bg-paper p-4">
      <div className="flex items-center justify-between"><span className="text-xs font-semibold text-ink">数据覆盖</span><span className={cn("h-2 w-2 rounded-full", fullyReady ? "bg-signal" : "bg-amber")} /></div>
      <p className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-ink">{connectors === null ? "—" : `${healthy} / ${total}`}</p>
      <p className="mt-1 text-[11px] leading-4 text-muted">{connectors === null ? "正在读取连接器状态" : unavailable ? `${healthy} 个正常 · ${unavailable} 个关闭或降级` : "全部公开信息源运行正常"}</p>
    </div>
  );
}

function NavContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <div className="flex h-full flex-col">
      <div className="px-5 pb-8 pt-6"><BrandMark /></div>
      <nav className="px-3" aria-label="主导航">
        <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted/70">Research desk</p>
        <div className="space-y-1">
          {navigation.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === href : pathname.startsWith(href);
            return (
              <Link key={href} href={href} onClick={onNavigate} className={cn("group relative flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium transition", active ? "bg-white text-ink shadow-[0_1px_2px_rgba(16,39,61,.05)]" : "text-muted hover:bg-white/60 hover:text-ink")}>
                {active && <span className="absolute -left-3 h-5 w-0.5 rounded-full bg-signal" />}
                <Icon className="h-[17px] w-[17px]" strokeWidth={1.8} />
                <span className="flex-1">{label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
      <div className="mt-auto p-4">
        <DataCoverage />
        <Link href="/settings" onClick={onNavigate} className="mt-3 flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium text-muted transition hover:bg-white/60 hover:text-ink"><Settings className="h-4 w-4" />系统能力与同步</Link>
      </div>
    </div>
  );
}

export function AppShell({ children }: React.PropsWithChildren) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<{ id:string; kind:string; title:string; summary:string; href:string }>>([]);
  const [searching, setSearching] = useState(false);
  useEffect(() => {
    const handler=(event:KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase()==="k") { event.preventDefault(); setSearchOpen(true); } };
    window.addEventListener("keydown",handler); return () => window.removeEventListener("keydown",handler);
  },[]);
  useEffect(() => {
    if (!searchOpen || query.trim().length<2) { setResults([]); return; }
    const controller=new AbortController(); const timer=window.setTimeout(() => { setSearching(true); void fetch(`/api/search?q=${encodeURIComponent(query.trim())}`,{signal:controller.signal}).then((response)=>response.ok?response.json():Promise.reject()).then((payload:{results:typeof results})=>setResults(payload.results)).catch(()=>undefined).finally(()=>setSearching(false)); },250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  },[query,searchOpen]);
  return <InternalAuthGate>
    <div className="min-h-screen bg-canvas text-ink">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[264px] border-r border-line bg-[#F2F2EE] lg:block"><NavContent /></aside>
      <header className="fixed inset-x-0 top-0 z-20 flex h-16 items-center border-b border-line bg-canvas/95 px-4 backdrop-blur lg:left-[264px] lg:px-8">
        <div className="flex w-full items-center justify-between gap-4">
          <Dialog.Root>
            <Dialog.Trigger asChild><Button variant="ghost" size="icon" className="lg:hidden" aria-label="打开导航"><Menu className="h-5 w-5" /></Button></Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/20 backdrop-blur-sm" />
              <Dialog.Content className="fixed inset-y-0 left-0 z-50 w-[min(88vw,320px)] border-r border-line bg-[#F2F2EE] shadow-2xl">
                <Dialog.Title className="sr-only">导航</Dialog.Title>
                <Dialog.Close asChild><Button variant="ghost" size="icon" className="absolute right-3 top-3 z-10" aria-label="关闭导航"><X className="h-5 w-5" /></Button></Dialog.Close>
                <NavContent />
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
          <div className="hidden items-center gap-2 text-xs text-muted sm:flex"><span className="font-semibold text-ink">美国市场</span><span>/</span><span>公开信息研究域</span></div>
          <button onClick={() => setSearchOpen(true)} className="flex h-9 w-full max-w-[360px] items-center gap-2 rounded-xl border border-line bg-paper px-3 text-left text-sm text-muted shadow-[0_1px_2px_rgba(16,39,61,.03)] transition hover:border-ink/20">
            <Search className="h-4 w-4" /><span className="flex-1 truncate">搜索主题、信息、ETF、对话或资料</span><kbd className="hidden rounded-md border border-line bg-canvas px-1.5 py-0.5 text-[10px] sm:inline">⌘ K</kbd>
          </button>
          <button className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink text-xs font-semibold text-white" aria-label="用户账户">YC</button>
        </div>
      </header>
      <main className="min-h-screen pt-16 lg:ml-[264px]">{children}</main>
      <Dialog.Root open={searchOpen} onOpenChange={setSearchOpen}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-ink/25 backdrop-blur-sm" /><Dialog.Content className="fixed left-1/2 top-[14vh] z-50 w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 overflow-hidden rounded-2xl border border-line bg-paper shadow-[0_30px_100px_rgba(16,39,61,.2)] outline-none"><Dialog.Title className="sr-only">全局搜索</Dialog.Title><Dialog.Description className="sr-only">搜索主题、每日信息、ETF、对话和已授权资料</Dialog.Description><div className="flex items-center gap-3 border-b border-line px-5"><Search className="h-5 w-5 text-signal" /><input autoFocus value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="输入主题、ETF、对话或资料名称" className="h-16 flex-1 bg-transparent text-base text-ink outline-none placeholder:text-muted/60" /><Dialog.Close asChild><Button variant="ghost" size="icon"><X className="h-4 w-4" /></Button></Dialog.Close></div><div className="max-h-[55vh] overflow-y-auto p-3">{query.trim().length<2?<p className="p-6 text-center text-sm text-muted">输入至少两个字符开始检索本地研究资产。</p>:searching?<p className="p-6 text-center text-sm text-muted">正在检索…</p>:results.length===0?<p className="p-6 text-center text-sm text-muted">没有匹配结果。可缩短关键词或先运行数据同步。</p>:<ul className="space-y-1">{results.map((item)=><li key={`${item.kind}-${item.id}`}><Dialog.Close asChild><Link href={item.href} className="block rounded-xl px-4 py-3 transition hover:bg-ink/[0.045]"><div className="flex items-center gap-2"><Badge>{item.kind==="theme"?"主题":item.kind==="knowledge"?"资料":item.kind==="conversation"?"对话":item.kind==="etf"?"ETF":"每日信息"}</Badge><p className="font-medium text-ink">{item.title}</p></div><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{item.summary}</p></Link></Dialog.Close></li>)}</ul>}</div></Dialog.Content></Dialog.Portal></Dialog.Root>
    </div>
  </InternalAuthGate>;
}
