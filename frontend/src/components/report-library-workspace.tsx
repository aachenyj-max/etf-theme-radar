"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  Archive,
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  Clock3,
  Command,
  FilterX,
  Folder,
  FolderOpen,
  Layers3,
  LoaderCircle,
  Pencil,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  X
} from "lucide-react";
import { ReportCard } from "@/components/report-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  ReportAssistantResult,
  ReportAssistantState,
  ReportDateRange,
  ReportFolderId,
  ReportLibraryFilters,
  ReportLibraryLoadState,
  ReportLibrarySnapshot,
  ReportMutationAction,
  ReportStatus,
  ResearchReportAsset
} from "@/lib/report-library";
import { reportLibraryGateway } from "@/services/report-library-gateway";
import { cn } from "@/lib/utils";

const defaultFilters: ReportLibraryFilters = { query: "", folder: "all", status: "all", dateRange: "all" };

const statusOptions: Array<{ value: "all" | ReportStatus; label: string }> = [
  { value: "all", label: "全部状态" },
  { value: "deep_research", label: "深度研究" },
  { value: "watch", label: "持续观察" },
  { value: "completed", label: "已完成" },
  { value: "draft", label: "草稿" },
  { value: "archived", label: "已归档" }
];

const dateOptions: Array<{ value: ReportDateRange; label: string }> = [
  { value: "all", label: "全部时间" },
  { value: "30d", label: "最近 30 天" },
  { value: "90d", label: "最近 90 天" },
  { value: "1y", label: "最近 1 年" }
];

const folderTone = {
  ai: "bg-[#EDF4F2] text-signal",
  energy: "bg-[#F8F1E6] text-amber",
  robotics: "bg-[#EEF2F7] text-[#45617B]",
  healthcare: "bg-[#F5EFF3] text-[#79586C]"
} as const;

const assistantCommands = [
  "查找所有机器人研究",
  "比较 AI ETF 报告",
  "总结最近的研究变化"
];

function SelectFilter({ label, value, options, onChange }: { label: string; value: string; options: Array<{ value: string; label: string }>; onChange: (value: string) => void }) {
  return (
    <label className="relative min-w-[150px]">
      <span className="sr-only">{label}</span>
      <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} className="h-11 w-full appearance-none rounded-xl border border-line bg-paper pl-3 pr-9 text-sm font-medium text-ink outline-none transition hover:border-ink/20 focus:border-signal focus:ring-2 focus:ring-signal/10">
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-3.5 h-4 w-4 text-muted" />
    </label>
  );
}

function LoadingLibrary() {
  return <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((item) => <div key={item} className="h-[330px] animate-pulse rounded-2xl border border-line bg-paper/70" />)}</div>;
}

function AssistantPalette({
  open,
  state,
  command,
  result,
  error,
  onOpenChange,
  onCommandChange,
  onSubmit,
  onApply
}: {
  open: boolean;
  state: ReportAssistantState;
  command: string;
  result: ReportAssistantResult | null;
  error: string | null;
  onOpenChange: (open: boolean) => void;
  onCommandChange: (command: string) => void;
  onSubmit: (event: FormEvent) => void;
  onApply: () => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/25 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-[14vh] z-50 w-[calc(100%-2rem)] max-w-[680px] -translate-x-1/2 overflow-hidden rounded-2xl border border-line bg-paper shadow-[0_30px_100px_rgba(16,39,61,.2)] outline-none">
          <Dialog.Title className="sr-only">询问研究资料库</Dialog.Title>
          <Dialog.Description className="sr-only">使用自然语言查找、比较或总结研究文件</Dialog.Description>
          <form onSubmit={onSubmit} className="flex items-center gap-3 border-b border-line px-5">
            {state === "running" ? <LoaderCircle className="h-5 w-5 animate-spin text-signal" /> : <Command className="h-5 w-5 text-signal" />}
            <input autoFocus value={command} onChange={(event) => onCommandChange(event.target.value)} placeholder="查找、比较或总结你的研究文件…" className="h-16 flex-1 bg-transparent text-base text-ink outline-none placeholder:text-muted/60" />
            <kbd className="rounded-md border border-line bg-canvas px-2 py-1 text-[10px] text-muted">ESC</kbd>
          </form>
          <div className="max-h-[58vh] overflow-y-auto p-3">
            {(state === "idle" || state === "closed") && <div><p className="px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.13em] text-muted">建议命令</p>{assistantCommands.map((suggestion) => <button key={suggestion} type="button" onClick={() => onCommandChange(suggestion)} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm text-ink transition hover:bg-canvas"><Search className="h-4 w-4 text-muted" /><span className="flex-1">{suggestion}</span><ArrowRight className="h-4 w-4 text-muted" /></button>)}</div>}
            {state === "running" && <div className="px-3 py-10 text-center"><p className="text-sm font-medium text-ink">正在检索研究资产</p><p className="mt-2 text-xs text-muted">只分析资料库中的文件与元数据</p></div>}
            {state === "failed" && <div className="rounded-xl border border-red-200 bg-red-50 p-5"><p className="text-sm font-semibold text-red-800">资料库助手未能完成命令</p><p className="mt-2 text-xs text-red-700">{error}</p></div>}
            {state === "ready" && result && <div className="rounded-xl border border-line bg-canvas p-5"><div className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-signal" /><h3 className="font-semibold text-ink">{result.title}</h3></div><p className="mt-3 text-sm leading-6 text-muted">{result.summary}</p><p className="mt-4 text-xs text-muted">{result.matchedReportIds.length} 份匹配文件</p>{result.suggestedFilters && <Button className="mt-5 w-full" type="button" onClick={onApply}>在资料库中显示结果<ArrowRight className="h-4 w-4" /></Button>}</div>}
          </div>
          <div className="flex items-center justify-between border-t border-line bg-canvas/70 px-5 py-3 text-[10px] text-muted"><span>Enter 执行命令</span><span>不会修改或删除文件</span></div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function ReportLibraryWorkspace() {
  const router = useRouter();
  const [filters, setFilters] = useState<ReportLibraryFilters>(defaultFilters);
  const [snapshot, setSnapshot] = useState<ReportLibrarySnapshot | null>(null);
  const [loadState, setLoadState] = useState<ReportLibraryLoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [mutations, setMutations] = useState<Record<string, ReportMutationAction>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<ResearchReportAsset | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ResearchReportAsset | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantState, setAssistantState] = useState<ReportAssistantState>("closed");
  const [assistantCommand, setAssistantCommand] = useState("");
  const [assistantResult, setAssistantResult] = useState<ReportAssistantResult | null>(null);
  const [assistantError, setAssistantError] = useState<string | null>(null);
  const assistantRequest = useRef(0);

  useEffect(() => {
    let active = true;
    setLoadState(snapshot ? "refreshing" : "loading");
    setError(null);
    reportLibraryGateway.listReports(filters)
      .then((nextSnapshot) => { if (active) { setSnapshot(nextSnapshot); setLoadState(nextSnapshot.state); } })
      .catch((reason) => { if (active) { setError(reason instanceof Error ? reason.message : "报告资料库读取失败。"); setLoadState("failed"); } });
    return () => { active = false; };
    // refreshKey 对应后端的显式重新拉取动作。
  }, [filters, refreshKey]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        setAssistantOpen(true);
        setAssistantState("idle");
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  const activeFilterCount = useMemo(() => Object.entries(filters).filter(([key, value]) => value !== defaultFilters[key as keyof ReportLibraryFilters]).length, [filters]);

  function updateFilter<Key extends keyof ReportLibraryFilters>(key: Key, value: ReportLibraryFilters[Key]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function setMutation(reportId: string, action?: ReportMutationAction) {
    setMutations((current) => {
      const next = { ...current };
      if (action) next[reportId] = action;
      else delete next[reportId];
      return next;
    });
  }

  function openReport(reportId: string) {
    router.push(`/reports/${encodeURIComponent(reportId)}`);
  }

  async function renameReport(event: FormEvent) {
    event.preventDefault();
    if (!renameTarget || !renameValue.trim()) return;
    const target = renameTarget;
    setRenameTarget(null);
    setMutation(target.id, "renaming");
    try {
      await reportLibraryGateway.renameReport(target.id, renameValue.trim());
      setNotice("报告名称已更新。");
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "重命名失败。");
    } finally {
      setMutation(target.id);
    }
  }

  async function archiveReport(report: ResearchReportAsset) {
    setMutation(report.id, "archiving");
    try {
      await reportLibraryGateway.archiveReport(report.id);
      setNotice("报告已归档，可通过“已归档”筛选查看。");
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "归档失败。");
    } finally {
      setMutation(report.id);
    }
  }

  async function deleteReport() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    setMutation(target.id, "deleting");
    try {
      await reportLibraryGateway.deleteReport(target.id);
      setNotice("报告已移入删除状态，不再显示于资料库。");
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "删除失败。");
    } finally {
      setMutation(target.id);
    }
  }

  async function askLibrary(event: FormEvent) {
    event.preventDefault();
    if (!assistantCommand.trim()) return;
    const requestId = ++assistantRequest.current;
    setAssistantState("running");
    setAssistantError(null);
    try {
      const result = await reportLibraryGateway.askLibrary(assistantCommand.trim());
      if (requestId === assistantRequest.current) { setAssistantResult(result); setAssistantState("ready"); }
    } catch (reason) {
      if (requestId === assistantRequest.current) { setAssistantError(reason instanceof Error ? reason.message : "资料库命令执行失败。"); setAssistantState("failed"); }
    }
  }

  function applyAssistantResult() {
    if (!assistantResult?.suggestedFilters) return;
    setFilters((current) => ({ ...current, ...assistantResult.suggestedFilters }));
    setAssistantOpen(false);
  }

  return (
    <div className="mx-auto max-w-[1500px] px-5 py-10 sm:px-8 sm:py-14 xl:px-12">
      <header className="border-b border-line pb-9">
        <div className="flex flex-wrap items-center gap-2"><Badge className="border-signal/20 bg-signal/[0.07] text-signal"><Layers3 className="mr-1 h-3 w-3" />研究档案</Badge><span className="text-xs text-muted">版本、审计与证据附件统一归档</span></div>
        <div className="mt-6 flex flex-col gap-7 xl:flex-row xl:items-end xl:justify-between">
          <div><p className="text-sm font-semibold uppercase tracking-[0.14em] text-signal">Report Library</p><h1 className="mt-3 text-[clamp(2.5rem,5vw,4.7rem)] font-semibold leading-[1.02] tracking-[-0.058em] text-ink">我的研究资料库</h1><p className="mt-4 max-w-2xl text-base leading-7 text-muted">集中管理主题报告、事件研究、证据简报和历史版本。</p><p className="mt-1 text-xs text-muted/70">My Research Library</p></div>
          <div className="flex items-center gap-6 border-l-2 border-signal pl-5"><div><p className="text-2xl font-semibold tracking-[-0.04em] text-ink">{snapshot?.activeCount ?? "—"}</p><p className="mt-1 text-xs text-muted">活跃研究</p></div><div><p className="text-2xl font-semibold tracking-[-0.04em] text-ink">{snapshot?.archivedCount ?? "—"}</p><p className="mt-1 text-xs text-muted">归档文件</p></div></div>
        </div>
      </header>

      <button type="button" onClick={() => { setAssistantOpen(true); setAssistantState("idle"); }} className="group mt-7 flex w-full items-center gap-4 rounded-2xl border border-line bg-paper p-4 text-left shadow-card transition hover:border-ink/20 sm:px-5">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-signal/[0.08] text-signal"><Sparkles className="h-5 w-5" /></span>
        <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink">询问你的研究资料库</p><p className="mt-1 truncate text-xs text-muted">查找机器人研究、比较 AI ETF 报告，或总结最近变化</p></div>
        <kbd className="hidden rounded-lg border border-line bg-canvas px-2.5 py-1.5 text-[10px] text-muted sm:block">⌘ K</kbd>
        <ArrowRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5" />
      </button>

      <section className="mt-8">
        <div className="mb-4 flex items-end justify-between"><div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-signal">Folder view</p><h2 className="mt-1 text-xl font-semibold tracking-[-0.025em] text-ink">研究文件夹</h2></div><button type="button" onClick={() => updateFilter("folder", "all")} className="text-xs font-medium text-muted hover:text-ink">查看全部</button></div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(snapshot?.folders ?? []).map((folder) => {
            const selected = filters.folder === folder.id;
            return <button key={folder.id} type="button" aria-pressed={selected} onClick={() => updateFilter("folder", selected ? "all" : folder.id)} className={cn("group rounded-2xl border bg-paper p-5 text-left shadow-card transition hover:-translate-y-0.5 hover:border-ink/20", selected ? "border-signal ring-1 ring-signal/10" : "border-line")}><div className="flex items-start justify-between"><span className={cn("grid h-11 w-11 place-items-center rounded-xl", folderTone[folder.id])}>{selected ? <FolderOpen className="h-5 w-5" /> : <Folder className="h-5 w-5" />}</span><span className="font-mono text-xs font-semibold text-muted">{String(folder.reportCount).padStart(2, "0")}</span></div><h3 className="mt-5 font-semibold text-ink">{folder.label}</h3><p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted/70">{folder.englishLabel}</p></button>;
          })}
        </div>
      </section>

      <section className="mt-9">
        <div className="flex flex-col gap-3 rounded-2xl border border-line bg-paper p-3 shadow-card lg:flex-row">
          <label className="flex h-11 min-w-0 flex-1 items-center gap-3 px-2"><Search className="h-4 w-4 text-muted" /><input value={filters.query} onChange={(event) => updateFilter("query", event.target.value)} aria-label="搜索报告" placeholder="搜索报告、主题或标签" className="h-full min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-muted/65" /></label>
          <div className="flex flex-col gap-2 sm:flex-row"><SelectFilter label="报告状态" value={filters.status} options={statusOptions} onChange={(value) => updateFilter("status", value as ReportLibraryFilters["status"])} /><SelectFilter label="更新时间" value={filters.dateRange} options={dateOptions} onChange={(value) => updateFilter("dateRange", value as ReportDateRange)} /><Button variant="outline" size="icon" onClick={() => setFilters(defaultFilters)} disabled={activeFilterCount === 0} aria-label="清除筛选"><FilterX className="h-4 w-4" /></Button><Button variant="ghost" size="icon" onClick={() => setRefreshKey((value) => value + 1)} aria-label="刷新资料库"><RefreshCw className={loadState === "refreshing" ? "h-4 w-4 animate-spin" : "h-4 w-4"} /></Button></div>
        </div>
      </section>

      <section className="mt-7" aria-live="polite">
        <div className="mb-5 flex items-center justify-between"><div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-signal">Research assets</p><h2 className="mt-1 text-xl font-semibold tracking-[-0.025em] text-ink">研究报告</h2></div><span className="text-xs text-muted">{snapshot ? `${snapshot.reports.length} / ${snapshot.totalBeforeFilters} 份文件` : "正在读取"}</span></div>
        {(loadState === "idle" || loadState === "loading") && <LoadingLibrary />}
        {loadState === "failed" && <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center"><AlertCircle className="mx-auto h-7 w-7 text-red-700" /><p className="mt-3 font-semibold text-red-800">报告资料库暂时无法读取</p><p className="mt-2 text-sm text-red-700">{error}</p><Button variant="outline" className="mt-5" onClick={() => setRefreshKey((value) => value + 1)}>重新加载</Button></div>}
        {loadState === "empty" && <div className="rounded-2xl border border-dashed border-ink/20 bg-paper px-6 py-16 text-center"><BookOpen className="mx-auto h-8 w-8 text-muted" /><h3 className="mt-4 text-xl font-semibold text-ink">没有符合条件的研究文件</h3><p className="mt-2 text-sm text-muted">调整主题文件夹、状态、日期或搜索条件。</p><Button variant="outline" className="mt-5" onClick={() => setFilters(defaultFilters)}>清除筛选</Button></div>}
        {snapshot && (loadState === "ready" || loadState === "refreshing") && <div className={loadState === "refreshing" ? "grid gap-4 opacity-55 transition md:grid-cols-2 2xl:grid-cols-3" : "grid gap-4 transition md:grid-cols-2 2xl:grid-cols-3"}>{snapshot.reports.map((report) => <ReportCard key={report.id} report={report} mutation={mutations[report.id]} onOpen={openReport} onRename={(item) => { setRenameTarget(item); setRenameValue(item.title); }} onArchive={archiveReport} onDelete={setDeleteTarget} />)}</div>}
      </section>

      <AssistantPalette open={assistantOpen} state={assistantState} command={assistantCommand} result={assistantResult} error={assistantError} onOpenChange={(open) => { setAssistantOpen(open); if (!open) { assistantRequest.current += 1; setAssistantState("closed"); } }} onCommandChange={(command) => { setAssistantCommand(command); setAssistantState("idle"); setAssistantResult(null); }} onSubmit={askLibrary} onApply={applyAssistantResult} />

      <Dialog.Root open={renameTarget !== null} onOpenChange={(open) => { if (!open) setRenameTarget(null); }}>
        <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-ink/20 backdrop-blur-sm" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-paper p-6 shadow-2xl outline-none"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-ink/[0.055] text-ink"><Pencil className="h-4 w-4" /></span><div><Dialog.Title className="font-semibold text-ink">重命名报告</Dialog.Title><Dialog.Description className="mt-1 text-xs text-muted">只修改资料库名称，不修改报告正文与引用。</Dialog.Description></div></div><form onSubmit={renameReport}><input autoFocus value={renameValue} onChange={(event) => setRenameValue(event.target.value)} className="mt-6 h-12 w-full rounded-xl border border-line bg-canvas px-4 text-sm text-ink outline-none focus:border-signal focus:ring-2 focus:ring-signal/10" /><div className="mt-6 flex justify-end gap-2"><Dialog.Close asChild><Button variant="ghost">取消</Button></Dialog.Close><Button type="submit" disabled={!renameValue.trim()}><Check className="h-4 w-4" />保存名称</Button></div></form></Dialog.Content></Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={deleteTarget !== null} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-ink/20 backdrop-blur-sm" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-paper p-6 shadow-2xl outline-none"><span className="grid h-11 w-11 place-items-center rounded-xl bg-red-50 text-red-700"><Trash2 className="h-5 w-5" /></span><Dialog.Title className="mt-5 text-lg font-semibold text-ink">删除这份报告？</Dialog.Title><Dialog.Description className="mt-2 text-sm leading-6 text-muted">“{deleteTarget?.title}”将从当前资料库移除。后端采用软删除，以保留审计记录。</Dialog.Description><div className="mt-6 flex justify-end gap-2"><Dialog.Close asChild><Button variant="ghost">取消</Button></Dialog.Close><Button onClick={deleteReport} className="bg-red-700 hover:bg-red-800"><Trash2 className="h-4 w-4" />确认删除</Button></div></Dialog.Content></Dialog.Portal>
      </Dialog.Root>

      {notice && <div className="fixed bottom-6 right-6 z-50 flex max-w-sm items-center gap-3 rounded-xl border border-line bg-ink px-4 py-3 text-sm text-white shadow-2xl"><Check className="h-4 w-4 text-[#8FD5C7]" /><span className="flex-1">{notice}</span><button onClick={() => setNotice(null)} aria-label="关闭通知"><X className="h-4 w-4 text-white/65" /></button></div>}
    </div>
  );
}
