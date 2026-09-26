"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getChat,
  listCustomers,
  myThreads,
  sendChat,
  type ChatMessage,
  type ThreadRow,
  type ThreadStatus,
} from "@/lib/api";
import { useTraceStream } from "@/lib/useTraceStream";
import { ThreadHistory } from "./ThreadHistory";

const OPEN: ThreadStatus = {
  status: "open",
  closed_by: null,
  reason: null,
  updated_at: null,
};

/**
 * Support Chat: one customer, their conversations, and nothing else.
 *
 * This is the customer-facing half of the system and it shows only what a customer would
 * be shown — what was said, and whether the conversation is still open. Tool calls,
 * policy verdicts, Jev scores and approval queues all live in the Support Dashboard,
 * which is a separate application for a different audience.
 *
 * Two things stop the composer, and the difference matters to the person typing. A
 * *pending approval* is temporary: someone is deciding, and the answer will arrive here
 * by itself. *Closed* is final: the issue was resolved, and anything new belongs in a new
 * conversation.
 */
export function Conversation({ initialThreadId }: { initialThreadId?: string }) {
  const router = useRouter();

  const [customers, setCustomers] = useState<string[]>([]);
  const [customerId, setCustomerId] = useState("cust-1");
  const [threads, setThreads] = useState<ThreadRow[]>([]);
  const [threadId, setThreadId] = useState<string | null>(initialThreadId ?? null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ThreadStatus>(OPEN);
  const [pending, setPending] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void listCustomers()
      .then((data) => setCustomers(data.customers.map((c) => c.customer_id)))
      .catch(() => setCustomers([]));
  }, []);

  const loadHistory = useCallback(async (who: string) => {
    try {
      setThreads((await myThreads(who)).threads);
    } catch {
      setThreads([]);
    }
  }, []);

  const loadThread = useCallback(async (id: string) => {
    try {
      const state = await getChat(id);
      setMessages(state.messages);
      setStatus(state.status);
      setPending(state.pending !== null);
      setCustomerId(state.customer_id);
      return state.customer_id;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const who = initialThreadId ? await loadThread(initialThreadId) : null;
      void loadHistory(who ?? customerId);
    })();
    // The history follows whichever customer the open thread belongs to.
  }, [initialThreadId, loadThread, loadHistory, customerId]);

  // A support agent replying, or an approval being resolved, both land here.
  useTraceStream((changed) => {
    if (threadId && changed.includes(threadId)) void loadThread(threadId);
    void loadHistory(customerId);
  });

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, busy]);

  const locked = busy || pending || status.status === "closed";

  async function send() {
    const text = draft.trim();
    if (!text || locked) return;

    setBusy(true);
    setError(null);
    setMessages((prior) => [...prior, { role: "customer", text, author: null }]);
    setDraft("");
    try {
      const state = await sendChat(customerId, text, threadId);
      setMessages(state.messages);
      setStatus(state.status);
      setPending(state.pending !== null);
      void loadHistory(customerId);
      if (!threadId) {
        setThreadId(state.thread_id);
        // `history.replaceState`, not `router.replace`: this only needs the address bar
        // to name the new conversation so a reload resumes it. A router navigation would
        // remount this component mid-turn and lose the thread it just started, which is
        // how the second message ended up in a second conversation.
        window.history.replaceState(null, "", `/c/${encodeURIComponent(state.thread_id)}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setMessages((prior) => prior.slice(0, -1));
      setDraft(text);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[calc(100dvh-7rem)] min-h-96 flex-col gap-4 lg:flex-row">
      <ThreadHistory
        threads={threads}
        customerId={customerId}
        activeId={threadId}
        onChanged={(deleted) => {
          void loadHistory(customerId);
          if (deleted === threadId) router.push("/");
        }}
      />

      <div
        className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <header
          className="flex flex-wrap items-center gap-2 border-b px-4 py-2.5"
          style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
        >
          <label className="flex items-center gap-1.5">
            <span className="text-[0.72rem]" style={{ color: "var(--text-faint)" }}>
              signed in as
            </span>
            <select
              className="mono rounded px-2 py-1 text-[0.75rem] outline-none disabled:opacity-60"
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border-strong)",
                color: "var(--text)",
              }}
              value={customerId}
              disabled={threadId !== null}
              onChange={(e) => {
                setCustomerId(e.target.value);
                void loadHistory(e.target.value);
              }}
            >
              {(customers.length ? customers : [customerId]).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>

          {status.status === "closed" && (
            <span
              className="chip"
              style={{ background: "var(--surface)", color: "var(--text-faint)" }}
            >
              closed
            </span>
          )}
        </header>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {messages.length === 0 && !busy && (
            <p className="text-[0.8rem]" style={{ color: "var(--text-faint)" }}>
              Hello — how can we help with your order?
            </p>
          )}

          {messages.map((message, i) => (
            <Bubble key={i} message={message} />
          ))}

          {busy && (
            <p className="text-[0.75rem]" style={{ color: "var(--text-faint)" }}>
              typing…
            </p>
          )}

          {pending && (
            <Notice tone="review">
              Someone from support is looking at this now. The answer will appear here.
            </Notice>
          )}

          {status.status === "closed" && (
            <Notice tone="dim">
              This conversation was closed
              {status.closed_by === "agent" ? " once your issue was resolved" : " by support"}
              {status.reason ? ` — ${status.reason}` : ""}. Start a new one if anything
              else comes up.
            </Notice>
          )}

          <div ref={bottom} />
        </div>

        <div className="border-t p-3" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-end gap-2">
            <textarea
              className="min-h-11 flex-1 rounded px-2.5 py-2 text-[0.82rem] outline-none disabled:opacity-60"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border-strong)",
                color: "var(--text)",
              }}
              rows={2}
              value={draft}
              disabled={locked}
              placeholder={
                status.status === "closed"
                  ? "This conversation is closed."
                  : pending
                    ? "Waiting on support…"
                    : "Message support — enter to send"
              }
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <button
              onClick={() => void send()}
              disabled={locked || !draft.trim()}
              className="rounded px-3 py-2 text-[0.8rem] font-semibold transition disabled:opacity-40"
              style={{ background: "var(--jev)", color: "var(--surface)" }}
            >
              {busy ? "…" : "Send"}
            </button>
          </div>

          {error && (
            <p className="mt-2 text-[0.75rem]" style={{ color: "var(--deny)" }}>
              {error}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function Notice({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone: "review" | "dim";
}) {
  return (
    <div
      className="rounded p-3 text-[0.78rem]"
      style={
        tone === "review"
          ? { background: "var(--review-soft)", color: "var(--review)" }
          : { background: "var(--surface-2)", color: "var(--text-dim)" }
      }
    >
      {children}
    </div>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const mine = message.role === "customer";
  const human = message.role === "human";

  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[80%]">
        {human && (
          <p className="mb-0.5 text-[0.65rem]" style={{ color: "var(--human)" }}>
            {message.author ?? "support"} · support team
          </p>
        )}
        <div
          className="rounded-lg px-3 py-2 text-[0.82rem] leading-relaxed whitespace-pre-wrap"
          style={{
            background: mine
              ? "var(--jev-soft)"
              : human
                ? "var(--human-soft)"
                : "var(--surface-2)",
            color: "var(--text)",
            border: human ? "1px solid var(--human)" : "1px solid var(--border)",
          }}
        >
          {message.text}
        </div>
      </div>
    </div>
  );
}
