"use client";

import Link from "next/link";
import { useState } from "react";
import { ago, deleteMyThread, type ThreadRow } from "@/lib/api";

/** The customer's own past conversations, newest first. */
export function ThreadHistory({
  threads,
  customerId,
  activeId,
  onChanged,
}: {
  threads: ThreadRow[];
  customerId: string;
  activeId: string | null;
  onChanged: (deleted: string) => void;
}) {
  return (
    <aside
      className="flex w-full shrink-0 flex-col overflow-hidden rounded-lg lg:w-72"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <header
        className="flex items-center gap-2 border-b px-3 py-2.5"
        style={{ borderColor: "var(--border)" }}
      >
        <h2 className="text-[0.8rem] font-semibold">Your conversations</h2>
        <Link
          href="/"
          className="ml-auto rounded px-2 py-1 text-[0.72rem]"
          style={{ border: "1px solid var(--border-strong)", color: "var(--text-dim)" }}
        >
          New
        </Link>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {threads.length === 0 && (
          <p className="p-3 text-[0.75rem]" style={{ color: "var(--text-faint)" }}>
            Nothing yet. Anything you send will be kept here.
          </p>
        )}

        {threads.map((thread) => (
          <Row
            key={thread.thread_id}
            thread={thread}
            customerId={customerId}
            active={thread.thread_id === activeId}
            onDeleted={() => onChanged(thread.thread_id)}
          />
        ))}
      </div>
    </aside>
  );
}

function Row({
  thread,
  customerId,
  active,
  onDeleted,
}: {
  thread: ThreadRow;
  customerId: string;
  active: boolean;
  onDeleted: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const closed = thread.status === "closed";

  async function remove() {
    setBusy(true);
    try {
      await deleteMyThread(thread.thread_id, customerId);
      onDeleted();
    } catch {
      setBusy(false);
      setAsking(false);
    }
  }

  return (
    <div
      className="border-b px-3 py-2"
      style={{
        borderColor: "var(--border)",
        background: active ? "var(--jev-soft)" : "transparent",
        borderLeft: active ? "3px solid var(--jev)" : "3px solid transparent",
      }}
    >
      <Link href={`/c/${encodeURIComponent(thread.thread_id)}`} className="block">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[0.78rem] font-medium">
            {thread.title ?? "New conversation"}
          </span>
          {closed && (
            <span
              className="chip ml-auto shrink-0"
              style={{ background: "var(--surface-2)", color: "var(--text-faint)" }}
            >
              closed
            </span>
          )}
        </div>
        <p
          className="mt-0.5 line-clamp-1 text-[0.7rem]"
          style={{ color: "var(--text-dim)" }}
        >
          {thread.opening_message}
        </p>
      </Link>

      <div className="mt-1 flex items-center gap-2">
        <span className="text-[0.62rem]" style={{ color: "var(--text-faint)" }}>
          {ago(thread.last_at)}
        </span>

        {asking ? (
          <span className="ml-auto flex items-center gap-1.5">
            <button
              onClick={() => void remove()}
              disabled={busy}
              className="rounded px-1.5 py-0.5 text-[0.65rem] font-semibold disabled:opacity-50"
              style={{ background: "var(--deny)", color: "var(--surface)" }}
            >
              {busy ? "…" : "Delete"}
            </button>
            <button
              onClick={() => setAsking(false)}
              className="text-[0.65rem]"
              style={{ color: "var(--text-dim)" }}
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            onClick={() => setAsking(true)}
            className="ml-auto text-[0.65rem] hover:underline"
            style={{ color: "var(--text-faint)" }}
            title="Delete this conversation"
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
