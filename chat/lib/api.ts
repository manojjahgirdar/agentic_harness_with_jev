/**
 * The chat's view of the support API.
 *
 * Deliberately smaller than the dashboard's client: this application is customer-facing,
 * so it can reach its own conversations and nothing else. There is no call here for
 * listing every thread, reading a decision trace, or resolving an approval, because a
 * customer has no business with any of them.
 */

export const API =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export interface ChatMessage {
  role: "customer" | "agent" | "human";
  text: string;
  author: string | null;
}

export interface ThreadStatus {
  status: "open" | "closed";
  closed_by: string | null;
  reason: string | null;
  updated_at: string | null;
}

export interface ChatState {
  thread_id: string;
  customer_id: string;
  messages: ChatMessage[];
  /** Set while a turn waits on a support decision. Shape is not the chat's business. */
  pending: unknown | null;
  status: ThreadStatus;
}

export interface ThreadRow {
  thread_id: string;
  title: string | null;
  opening_message: string | null;
  last_at: string;
  turns: number;
  status: "open" | "closed";
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json() as Promise<T>;
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const parsed = await res.json();
      if (parsed?.detail) detail = String(parsed.detail);
    } catch {
      // a non-JSON error body is still an error; the status line will do
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function listCustomers() {
  return get<{ customers: { customer_id: string; orders: number }[] }>(
    "/api/customers",
  );
}

export function myThreads(customerId: string) {
  return get<{ customer_id: string; threads: ThreadRow[] }>(
    `/api/customers/${encodeURIComponent(customerId)}/threads`,
  );
}

export function getChat(threadId: string) {
  return get<ChatState>(`/api/chat/${encodeURIComponent(threadId)}`);
}

export function sendChat(customerId: string, message: string, threadId: string | null) {
  return send<ChatState>("/api/chat", "POST", {
    customer_id: customerId,
    message,
    thread_id: threadId,
  });
}

export function deleteMyThread(threadId: string, customerId: string) {
  return send<{ deleted: boolean }>(
    `/api/chat/${encodeURIComponent(threadId)}?customer_id=${encodeURIComponent(customerId)}`,
    "DELETE",
  );
}

export function ago(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${Math.floor(seconds)}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
