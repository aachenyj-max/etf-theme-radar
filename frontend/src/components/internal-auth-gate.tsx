"use client";

import { FormEvent, useEffect, useState } from "react";

type Session = { enabled: boolean; authenticated: boolean; username: string };

export function InternalAuthGate({ children }: React.PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void fetch("/api/auth/session", { headers: { Accept: "application/json" } })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("session unavailable")))
      .then((payload: Session) => setSession(payload))
      .catch(() => setSession({ enabled: true, authenticated: false, username: "" }));
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) throw new Error("账号或密码错误");
      const payload = await response.json() as Session;
      setPassword("");
      setSession({ enabled: true, authenticated: true, username: payload.username });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  if (session === null) return <div className="grid min-h-screen place-items-center bg-canvas text-sm text-muted">正在检查内部访问权限…</div>;
  if (!session.enabled || session.authenticated) return <>{children}</>;

  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-5 text-ink">
      <form onSubmit={login} className="w-full max-w-sm rounded-2xl border border-line bg-paper p-7 shadow-[0_24px_70px_rgba(16,39,61,.12)]">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-signal">ETF Theme Radar</p>
        <h1 className="mt-3 text-2xl font-semibold tracking-[-0.04em]">内部账号登录</h1>
        <p className="mt-2 text-sm leading-6 text-muted">请输入分配给你的账号和密码。登录后可使用全部研究页面。</p>
        <label className="mt-6 block text-sm font-medium">账号<input required autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} className="mt-2 h-11 w-full rounded-xl border border-line bg-white px-3 outline-none focus:border-signal" /></label>
        <label className="mt-4 block text-sm font-medium">密码<input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-2 h-11 w-full rounded-xl border border-line bg-white px-3 outline-none focus:border-signal" /></label>
        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
        <button disabled={submitting} className="mt-6 h-11 w-full rounded-xl bg-ink text-sm font-semibold text-white disabled:opacity-60">{submitting ? "正在登录…" : "登录"}</button>
      </form>
    </main>
  );
}
