"use client";

import { useState } from "react";
import { setThreadStatus } from "@/lib/api";
import type { ThreadStatus } from "@/lib/types";

/**
 * Close a resolved thread, or put one back in play.
 *
 * Closing is the support side of the conversation ending: the customer's composer locks,
 * and the thread stops appearing as live work in the queues above the table. It is not
 * deletion — everything the thread decided stays readable, which is the whole point of
 * keeping a trace.
 */
export function StatusControl({
  threadId,
  status,
  onChanged,
}: {
  threadId: string;
  status: ThreadStatus;
  onChanged: () => void;
}) {
  const [reason, setReason] = useState("");
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const closed = status.status === "closed";

  async function apply(next: "closed" | "open") {
    setBusy(true);
    setError(null);
    try {
      await setThreadStatus(threadId, next, "support", reason.trim() || undefined);
      setAsking(false);
      setReason("");
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (closed) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="chip"
          style={{ background: "var(--surface-2)", color: "var(--text-faint)" }}
        >
          closed by {status.closed_by ?? "support"}
        </span>
        {status.reason && (
          <span className="text-[0.72rem]" style={{ color: "var(--text-dim)" }}>
            {status.reason}
          </span>
        )}
        <button
          onClick={() => void apply("open")}
          disabled={busy}
          className="rounded px-2 py-1 text-[0.72rem] disabled:opacity-50"
          style={{ border: "1px solid var(--border-strong)", color: "var(--text-dim)" }}
        >
          {busy ? "…" : "Reopen"}
        </button>
        {error && (
          <span className="text-[0.72rem]" style={{ color: "var(--deny)" }}>
            {error}
          </span>
        )}
      </div>
    );
  }

  if (!asking) {
    return (
      <button
        onClick={() => setAsking(true)}
        className="rounded px-2 py-1 text-[0.72rem]"
        style={{ border: "1px solid var(--border-strong)", color: "var(--text-dim)" }}
        title="Mark this conversation resolved"
      >
        Close thread
      </button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        className="rounded px-2 py-1 text-[0.75rem] outline-none"
        style={{
          background: "var(--surface-2)",
          border: "1px solid var(--border-strong)",
          color: "var(--text)",
          minWidth: "16rem",
        }}
        placeholder="What was resolved? (optional, shown to the customer)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <button
        onClick={() => void apply("closed")}
        disabled={busy}
        className="rounded px-2 py-1 text-[0.72rem] font-semibold disabled:opacity-50"
        style={{ background: "var(--text-dim)", color: "var(--surface)" }}
      >
        {busy ? "…" : "Close"}
      </button>
      <button
        onClick={() => setAsking(false)}
        className="text-[0.72rem]"
        style={{ color: "var(--text-dim)" }}
      >
        Cancel
      </button>
      {error && (
        <span className="text-[0.72rem]" style={{ color: "var(--deny)" }}>
          {error}
        </span>
      )}
    </div>
  );
}
