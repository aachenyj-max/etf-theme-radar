"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { ArchiveRestore, Folder, LockKeyhole, Search, Share2, Trash2, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { KnowledgeItem, KnowledgeOperation } from "@/lib/knowledge-base";
import { knowledgeBaseGateway } from "@/services/knowledge-base-gateway";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const kindLabel: Record<string, string> = { note: "笔记", meeting_material: "会议材料", etf_material: "ETF 资料", upload: "上传文件", conversation_excerpt: "对话摘录", saved_reference: "保存引用" };

export function KnowledgeBaseWorkspace() {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [query, setQuery] = useState("");
  const [collection, setCollection] = useState<"all" | "private" | "shared">("all");
  const [recipient, setRecipient] = useState("");
  const [operation, setOperation] = useState<KnowledgeOperation | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => { void knowledgeBaseGateway.list().then(setItems).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false)); }, []);
  const visible = useMemo(() => items.filter(item => (collection === "all" || item.visibility === collection) && `${item.title} ${item.theme_id} ${item.kind}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())), [collection, items, query]);
  async function preview(item: KnowledgeItem, operationType: KnowledgeOperation["operation_type"]) {
    setError(""); setNotice("");
    try {
      const payload: Record<string, string> = operationType === "share" ? { subject_type: "user", subject_id: recipient.trim() } : {};
      if (operationType === "share" && !payload.subject_id) { setError("先填写共享对象，再预览共享范围。"); return; }
      setOperation(await knowledgeBaseGateway.preview(item.knowledge_item_id, operationType, payload));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法生成操作预览。"); }
  }
  async function confirm() {
    if (!operation) return;
    try { await knowledgeBaseGateway.confirm(operation); setNotice(operation.operation_type === "share" ? "共享已更新" : "操作已完成"); setOperation(null); setItems(await knowledgeBaseGateway.list()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "确认操作失败。"); }
  }
  const operationName = operation?.operation_type === "share" ? "共享" : operation?.operation_type === "delete" ? "删除" : "变更";
  return <div className="mx-auto max-w-7xl px-5 py-10 lg:px-8">
    <header className="border-b border-line pb-7"><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-signal">Private research materials</p><div className="mt-2 flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-3xl font-semibold tracking-[-0.04em] text-ink">个人知识库</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted">只显示你拥有或被明确共享的材料。研究 Agent 仅将它们作为标注的内部上下文。</p></div><div className="rounded-xl border border-line bg-paper px-4 py-3 text-xs text-muted"><LockKeyhole className="mr-2 inline h-4 w-4 text-signal" />默认仅自己可见</div></div></header>
    <section className="mt-7 grid gap-4 lg:grid-cols-[220px_1fr]"><aside className="rounded-2xl border border-line bg-paper p-4"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">智能集合</p><div className="mt-3 space-y-1">{([['all','全部资料'],['private','仅自己可见'],['shared','已共享']] as const).map(([key,label]) => <button key={key} type="button" onClick={() => setCollection(key)} className={`flex h-10 w-full items-center gap-2 rounded-lg px-3 text-left text-sm ${collection === key ? "bg-ink text-white" : "text-muted hover:bg-canvas"}`}><Folder className="h-4 w-4" />{label}</button>)}</div></aside><div><div className="flex flex-col gap-3 sm:flex-row"><label className="flex h-10 flex-1 items-center gap-2 rounded-xl border border-line bg-paper px-3"><Search className="h-4 w-4 text-muted" /><input aria-label="搜索知识库" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索标题、主题或材料类型" className="min-w-0 flex-1 bg-transparent text-sm outline-none" /></label><label className="flex h-10 items-center gap-2 rounded-xl border border-line bg-paper px-3 text-sm"><Users className="h-4 w-4 text-muted" /><span className="sr-only">共享对象</span><input aria-label="共享对象" value={recipient} onChange={event => setRecipient(event.target.value)} placeholder="共享对象" className="w-28 bg-transparent outline-none" /></label></div>{error && <p className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}{notice && <p className="mt-4 rounded-xl border border-signal/20 bg-signal/[0.06] p-3 text-sm text-signal">{notice}</p>}<div className="mt-5 grid gap-4 md:grid-cols-2">{loading ? <p className="text-sm text-muted">正在读取授权资料…</p> : visible.map(item => <article key={item.knowledge_item_id} className="rounded-2xl border border-line bg-paper p-5 shadow-card"><div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">{kindLabel[item.kind] ?? item.kind} · V{item.current_version}</p><h2 className="mt-2 font-semibold text-ink">{item.title}</h2></div><Badge className={item.visibility === "private" ? "border-signal/20 bg-signal/[0.07] text-signal" : "border-amber/20 bg-amber/[0.08] text-amber"}>{item.visibility === "private" ? "仅自己可见" : "已共享"}</Badge></div><p className="mt-4 text-xs text-muted">{item.theme_id || "未归类"} · {item.original_filename}</p><div className="mt-5 flex gap-2 border-t border-line pt-4"><Button size="sm" variant="outline" onClick={() => void preview(item, "share")} aria-label={`共享 ${item.title}`}><Share2 className="h-3.5 w-3.5" />共享</Button><Button size="sm" variant="ghost" onClick={() => void preview(item, "delete")} aria-label={`删除 ${item.title}`}><Trash2 className="h-3.5 w-3.5" />删除</Button></div></article>)}{!loading && visible.length === 0 && <p className="rounded-2xl border border-dashed border-line p-8 text-sm text-muted">没有匹配的授权资料。</p>}</div></div></section>
    <Dialog.Root open={Boolean(operation)} onOpenChange={open => { if (!open) setOperation(null); }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-ink/25 backdrop-blur-sm" /><Dialog.Content aria-describedby={undefined} className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-paper p-6 shadow-2xl"><Dialog.Title className="text-lg font-semibold text-ink">确认{operationName}</Dialog.Title><p className="mt-3 text-sm leading-6 text-muted">将对当前版本执行此操作。确认后令牌立即失效，网络失败不会自动重试。</p><pre className="mt-4 overflow-auto rounded-xl bg-canvas p-3 text-xs text-muted">{JSON.stringify(operation?.preview.changes ?? {}, null, 2)}</pre><div className="mt-6 flex justify-end gap-2"><Dialog.Close asChild><Button variant="ghost">取消</Button></Dialog.Close><Button onClick={() => void confirm()}>确认{operationName}</Button></div></Dialog.Content></Dialog.Portal></Dialog.Root>
  </div>;
}
