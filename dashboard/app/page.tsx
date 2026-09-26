"use client";

import { useCallback, useEffect, useState } from "react";
import { API, listThreads } from "@/lib/api";
import type { ThreadSummary } from "@/lib/types";
import { useTraceStream } from "@/lib/useTraceStream";
import { ActionQueue, type ActionItem } from "@/components/ActionQueue";
import { AttentionStrip } from "@/components/AttentionStrip";
import { ThreadTable } from "@/components/ThreadTable";

export default function Page() {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [threshold, setThreshold] = useState(0.5);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listThreads();
      // The API groups by customer; the table wants one flat list, newest first.
      const flat = data.customers.flatMap((c) => c.threads);
      flat.sort((a, b) => b.last_at.localeCompare(a.last_at));
      setThreads(flat);
      setThreshold(data.attention.frustration);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const connected = useTraceStream(() => void refresh());

  const pending = threads.filter((t) => t.pending_approval).length;

  // Approvals first: those threads are suspended mid-turn, waiting on a decision.
  const actions: ActionItem[] = [
    ...threads
      .filter((t) => t.pending_approval)
      .map((thread): ActionItem => ({ thread, kind: "approval" })),
    ...threads
      .filter((t) => t.awaiting_human)
      .map((thread): ActionItem => ({ thread, kind: "escalation" })),
  ];
  const blocked = new Set(actions.map((a) => a.thread.thread_id));

  // Still-moving threads first, then angriest: that is the order you would work it in.
  // Threads already listed above are left out — they are past "maybe".
  const attention = threads
    .filter((t) => t.needs_attention && !blocked.has(t.thread_id))
    .sort(
      (a, b) =>
        Number(b.is_live) - Number(a.is_live) ||
        (b.frustration_series.at(-1) ?? 0) - (a.frustration_series.at(-1) ?? 0),
    );

  return (
    <main className="mx-auto min-h-dvh w-full max-w-[1400px] px-6 pt-10 pb-16 lg:px-10">
      <header className="mb-6 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-lg font-semibold">Support Dashboard</h1>
        <span className="text-[0.75rem]" style={{ color: "var(--text-faint)" }}>
          {threads.length} thread{threads.length === 1 ? "" : "s"}
          {pending > 0 && (
            <span style={{ color: "var(--review)" }}> · {pending} awaiting approval</span>
          )}
        </span>
        <span
          className="ml-auto flex items-center gap-1.5 text-[0.7rem]"
          style={{ color: connected ? "var(--allow)" : "var(--text-faint)" }}
          title={connected ? "Live via server-sent events" : "Reconnecting…"}
        >
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ background: connected ? "var(--allow)" : "var(--text-faint)" }}
          />
          {connected ? "live" : "offline"}
        </span>
      </header>

      {error ? (
        <div className="card max-w-md p-5">
          <h2 className="text-sm font-semibold" style={{ color: "var(--deny)" }}>
            Cannot reach the trace API
          </h2>
          <p className="mt-2 text-[0.8rem]" style={{ color: "var(--text-dim)" }}>
            Expected it at <code className="mono">{API}</code>. Start it with:
          </p>
          <pre className="mono mt-2 rounded p-2" style={{ background: "var(--surface-2)" }}>
            uv run api.py
          </pre>
          <p className="mt-2 text-[0.72rem]" style={{ color: "var(--text-faint)" }}>
            {error}
          </p>
        </div>
      ) : (
        <>
          <ActionQueue items={actions} />
          <AttentionStrip threads={attention} threshold={threshold} />
          <ThreadTable threads={threads} onDeleted={refresh} />
        </>
      )}
    </main>
  );
}
