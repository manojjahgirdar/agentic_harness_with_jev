import type { CustomerGroup, Decision, ThreadDetail } from "./types";

export const API =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json() as Promise<T>;
}

export function listThreads() {
  return get<{
    customers: CustomerGroup[];
    latest_trace_id: number;
    attention: { frustration: number; window_minutes: number };
  }>("/api/threads");
}

/** Close a resolved thread, or put one back in play. */
export async function setThreadStatus(
  threadId: string,
  status: "closed" | "open",
  by: string,
  reason?: string,
) {
  const res = await fetch(
    `${API}/api/threads/${encodeURIComponent(threadId)}/${status === "closed" ? "close" : "reopen"}`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ by, reason }),
    },
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/** Forget a thread: its trace, its title and its checkpoints. There is no undo. */
export async function deleteThread(threadId: string) {
  const res = await fetch(`${API}/api/threads/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export function getThread(threadId: string) {
  return get<ThreadDetail>(`/api/threads/${encodeURIComponent(threadId)}`);
}

export async function resumeThread(threadId: string, decisions: Decision[]) {
  const res = await fetch(
    `${API}/api/threads/${encodeURIComponent(threadId)}/resume`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decisions, reviewer: "dashboard" }),
    },
  );
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

/** Send a human agent's reply into an escalated thread. The model is not invoked. */
export async function sendHumanReply(
  threadId: string,
  text: string,
  agent: string,
) {
  const res = await fetch(
    `${API}/api/threads/${encodeURIComponent(threadId)}/reply`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text, agent }),
    },
  );
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

/** Relative time, e.g. "3m ago". The trace is read live, so absolute stamps rarely help. */
export function ago(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${Math.floor(seconds)}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
