"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Clock3, FileText, MessageSquarePlus, PanelRightClose, PanelRightOpen, Send, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Conversation = {
  conversation_id: string;
  selected_theme_id: string;
  title: string;
  status: string;
  updated_at: string;
};

type ConversationMessage = {
  message_id: string;
  message_seq: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type ConversationEvent = {
  event_id: number;
  kind: "action_status" | "tool_summary" | "evidence_delta" | "answer_chunk" | "background_goal_created";
  action: string;
  status: string;
  elapsed_ms: number;
  source_count: number;
  safe_summary: string;
  answer_chunk: string;
  created_at: string;
};

type LinkedSummary = { conversation_id: string; conversation_summary: string; keywords: string[]; covered_to_seq: number };

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(String(response.status));
  return response.json() as Promise<T>;
}

function elapsedLabel(value: number): string {
  if (!value) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)} 秒` : `${value} ms`;
}

function ConversationRow({ conversation, selected, onSelect }: { conversation: Conversation; selected: boolean; onSelect: () => void }) {
  return <button type="button" onClick={onSelect} aria-current={selected ? "page" : undefined} className={cn(
    "group w-full border-l-2 px-4 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/40",
    selected ? "border-signal bg-signal/[0.08]" : "border-transparent hover:border-ink/25 hover:bg-ink/[0.025]",
  )}>
    <span className="block truncate text-sm font-semibold text-ink">{conversation.title}</span>
    <span className="mt-1 flex items-center justify-between gap-2 text-[10px] text-muted"><span className="truncate">{conversation.selected_theme_id}</span><span>{conversation.status === "active" ? "进行中" : conversation.status}</span></span>
  </button>;
}

export function ConversationResearchWorkspace({ fallback }: { fallback: ReactNode }) {
  const [mode, setMode] = useState<"loading" | "conversation" | "legacy">("loading");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [events, setEvents] = useState<ConversationEvent[]>([]);
  const [linkedSummaries, setLinkedSummaries] = useState<LinkedSummary[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [composer, setComposer] = useState("");
  const [newThemeId, setNewThemeId] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadConversations = useCallback(async () => {
    try {
      const payload = await getJson<{ conversations: Conversation[] }>("/api/conversations");
      setConversations(payload.conversations);
      setSelectedId((current) => current || payload.conversations[0]?.conversation_id || "");
      setMode("conversation");
    } catch (reason) {
      if (reason instanceof Error && ["404", "405"].includes(reason.message)) setMode("legacy");
      else { setMode("conversation"); setError("研究对话暂时无法读取，请稍后刷新。"); }
    }
  }, []);

  const loadSelected = useCallback(async (conversationId: string, afterEventId = 0) => {
    if (!conversationId) return;
    try {
      const [messagePayload, eventPayload, linkPayload] = await Promise.all([
        getJson<{ messages: ConversationMessage[] }>(`/api/conversations/${encodeURIComponent(conversationId)}/messages`),
        getJson<{ events: ConversationEvent[] }>(`/api/conversations/${encodeURIComponent(conversationId)}/events?after_event_id=${afterEventId}`),
        getJson<{ summaries: LinkedSummary[] }>(`/api/conversations/${encodeURIComponent(conversationId)}/links`),
      ]);
      setMessages(messagePayload.messages);
      setEvents((current) => {
        if (!afterEventId) return eventPayload.events;
        const known = new Set(current.map((item) => item.event_id));
        return [...current, ...eventPayload.events.filter((item) => !known.has(item.event_id))];
      });
      setLinkedSummaries(linkPayload.summaries);
      setError("");
    } catch {
      setError("对话状态读取失败；未自动重放任何写操作。");
    }
  }, []);

  useEffect(() => { void loadConversations(); }, [loadConversations]);
  useEffect(() => { if (mode === "conversation") { setEvents([]); void loadSelected(selectedId); } }, [mode, selectedId, loadSelected]);
  useEffect(() => {
    if (!selectedId || mode !== "conversation") return;
    const timer = window.setInterval(() => {
      const cursor = events.at(-1)?.event_id ?? 0;
      void loadSelected(selectedId, cursor);
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [events, loadSelected, mode, selectedId]);

  const selected = useMemo(() => conversations.find((item) => item.conversation_id === selectedId), [conversations, selectedId]);
  const lastAction = [...events].reverse().find((item) => item.action || item.safe_summary);
  const answerChunks = events.filter((item) => item.kind === "answer_chunk" && item.answer_chunk);

  async function createConversation() {
    if (!newThemeId.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/conversations", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected_theme_id: newThemeId.trim(), title: newTitle.trim() }),
      });
      if (!response.ok) throw new Error();
      const created = await response.json() as Conversation;
      setConversations((current) => [created, ...current]);
      setSelectedId(created.conversation_id); setNewThemeId(""); setNewTitle("");
    } catch { setError("新建对话失败；请确认已选主题后重试。"); }
    finally { setBusy(false); }
  }

  async function sendMessage() {
    if (!selectedId || !composer.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/conversations/${encodeURIComponent(selectedId)}/messages`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: composer.trim(), idempotency_key: crypto.randomUUID() }),
      });
      if (!response.ok) throw new Error();
      const payload = await response.json() as { message: ConversationMessage };
      setMessages((current) => [...current, payload.message]); setComposer("");
    } catch { setError("消息未发送；为避免重复写入，系统没有自动重试。"); }
    finally { setBusy(false); }
  }

  if (mode === "legacy") return <>{fallback}</>;
  if (mode === "loading") return <div className="mx-auto max-w-[1500px] px-4 py-10 text-sm text-muted">正在读取研究对话…</div>;

  return <div className="mx-auto max-w-[1600px] px-4 py-6 sm:px-7 xl:px-10">
    <header className="mb-5 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
      <div><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-signal">Conversation research desk</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.045em] text-ink">主题研究对话台</h1><p className="mt-2 text-sm text-muted">按对话保留证据、审计与下一步，不混入未授权历史。</p></div>
      <Button variant="outline" size="sm" onClick={() => setDrawerOpen((value) => !value)} aria-label={drawerOpen ? "关闭研究抽屉" : "打开研究抽屉"}>{drawerOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}{drawerOpen ? "收起抽屉" : "研究抽屉"}</Button>
    </header>
    <div className={cn("grid items-start gap-5", drawerOpen ? "xl:grid-cols-[260px_minmax(0,1fr)_300px]" : "xl:grid-cols-[260px_minmax(0,1fr)]")}>
      <aside aria-label="研究对话" className="overflow-hidden rounded-2xl border border-line bg-paper shadow-card xl:sticky xl:top-20">
        <div className="border-b border-line bg-ink px-4 py-4 text-paper"><div className="flex items-center justify-between"><p className="text-sm font-semibold">研究对话</p><span className="font-mono text-[10px] text-paper/55">{conversations.length}</span></div><p className="mt-1 text-[10px] text-paper/55">每条对话独立串行</p></div>
        <div className="max-h-[calc(100vh-240px)] overflow-auto py-2">{conversations.map((item) => <ConversationRow key={item.conversation_id} conversation={item} selected={item.conversation_id === selectedId} onSelect={() => setSelectedId(item.conversation_id)} />)}</div>
        <div className="border-t border-line p-3"><label className="sr-only" htmlFor="new-theme-id">已选主题 ID</label><input id="new-theme-id" value={newThemeId} onChange={(event) => setNewThemeId(event.target.value)} placeholder="已选主题 ID" className="w-full rounded-lg border border-line bg-canvas px-3 py-2 text-xs outline-none focus:border-signal" /><input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} placeholder="对话名称（可选）" className="mt-2 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-xs outline-none focus:border-signal" /><Button className="mt-2 w-full" size="sm" disabled={!newThemeId.trim() || busy} onClick={() => void createConversation()}><MessageSquarePlus className="h-3.5 w-3.5" />新建对话</Button></div>
      </aside>
      <main className="min-w-0 rounded-2xl border border-line bg-paper shadow-card">
        {error && <p role="alert" className="m-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        {selected ? <>
          <section className="border-b border-line p-5 sm:p-7"><div className="flex flex-wrap items-center justify-between gap-3"><Badge className="border-signal/20 bg-signal/[0.07] text-signal">{selected.selected_theme_id}</Badge><span className="font-mono text-[10px] text-muted">对话状态 · {selected.status}</span></div><h2 className="mt-4 text-2xl font-semibold tracking-[-0.04em] text-ink">{selected.title}</h2><div aria-live="polite" className="mt-5 grid gap-2 border-y border-line py-3 text-xs sm:grid-cols-3"><span className="flex items-center gap-2 text-ink"><Sparkles className="h-3.5 w-3.5 text-signal" />{lastAction?.action || lastAction?.safe_summary || "等待第一条审计事件"}</span><span className="flex items-center gap-2 text-muted"><Clock3 className="h-3.5 w-3.5" />耗时 {elapsedLabel(lastAction?.elapsed_ms ?? 0)}</span><span className="text-muted">来源 {lastAction?.source_count ?? 0}</span></div></section>
          <section className="min-h-[380px] space-y-5 bg-[linear-gradient(to_bottom,transparent_31px,rgba(16,39,61,.035)_32px)] bg-[length:100%_32px] p-5 sm:p-7"><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-muted">对话流 / 不可变顺序</p>{messages.map((message) => <article key={message.message_id} className={cn("max-w-[86%] rounded-2xl px-4 py-3 text-sm leading-6", message.role === "user" ? "ml-auto bg-ink text-paper" : "border border-line bg-canvas text-ink")}><p className="mb-1 text-[10px] opacity-60">{message.role === "user" ? "你" : "研究 Agent"} · #{message.message_seq}</p>{message.content}</article>)}{answerChunks.map((event) => <article key={event.event_id} className="max-w-[86%] rounded-2xl border border-signal/20 bg-signal/[0.055] px-4 py-3 text-sm leading-6 text-ink"><p className="mb-1 text-[10px] text-signal">研究 Agent · 已校验片段</p>{event.answer_chunk}</article>)}{!messages.length && !answerChunks.length && <div className="rounded-xl border border-dashed border-line bg-canvas/70 p-6 text-sm text-muted">从左侧新建一个已选主题对话，或选择已有对话继续研究。</div>}</section>
          <form onSubmit={(event) => { event.preventDefault(); void sendMessage(); }} className="border-t border-line p-4"><label className="sr-only" htmlFor="conversation-composer">继续研究</label><div className="flex gap-2"><textarea id="conversation-composer" value={composer} onChange={(event) => setComposer(event.target.value)} placeholder="继续追问、比较或要求补证…" rows={2} className="min-w-0 flex-1 resize-none rounded-xl border border-line bg-canvas px-3 py-2 text-sm outline-none focus:border-signal" /><Button type="submit" disabled={!composer.trim() || busy} aria-label="发送研究消息"><Send className="h-4 w-4" /></Button></div><p className="mt-2 text-[10px] text-muted">消息只提交一次；网络中断不会自动重放写操作。</p></form>
        </> : <div className="p-8 text-sm text-muted">在左侧输入已选主题 ID，创建第一条研究对话。</div>}
      </main>
      {drawerOpen && <aside aria-label="研究抽屉" className="rounded-2xl border border-line bg-paper shadow-card xl:sticky xl:top-20"><div className="border-b border-line p-5"><p className="text-sm font-semibold text-ink">研究抽屉</p><p className="mt-1 text-[11px] leading-5 text-muted">只展示安全审计摘要和已授权对话总结。</p></div><div className="space-y-5 p-5"><section><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-muted">审计摘要</p><ol className="mt-3 space-y-2">{events.filter((item) => item.safe_summary || item.action).slice(-5).reverse().map((item) => <li key={item.event_id} className="rounded-lg bg-canvas p-3 text-xs leading-5 text-ink">{item.action || item.safe_summary}<span className="mt-1 block text-[10px] text-muted">{item.kind} · {elapsedLabel(item.elapsed_ms)}</span></li>)}{!events.length && <li className="text-xs text-muted">尚无持久化审计事件</li>}</ol></section><section><p className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.14em] text-muted"><FileText className="h-3.5 w-3.5" />显式关联</p>{linkedSummaries.length ? <div className="mt-3 space-y-2">{linkedSummaries.map((item) => <article key={item.conversation_id} className="rounded-lg border border-line p-3 text-xs"><p className="font-semibold text-ink">{item.conversation_id}</p><p className="mt-1 leading-5 text-muted">{item.conversation_summary}</p></article>)}</div> : <p className="mt-3 text-xs leading-5 text-muted">没有显式关联其他对话</p>}</section></div></aside>}
    </div>
  </div>;
}
