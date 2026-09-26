"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ago, deleteThread } from "@/lib/api";
import type { ThreadSummary } from "@/lib/types";
import { Sparkline } from "./Meters";

const PER_PAGE = 10;

/**
 * Every thread as one row, newest activity first.
 *
 * Flat rather than grouped by customer: the question this answers is "which conversation
 * needs me", and that is decided by what was asked, whether it escalated and where the
 * frustration went — none of which respect customer boundaries. The customer is still a
 * column, so the grouping is a sort away rather than a structure everything else bends
 * around.
 */
export function ThreadTable({
  threads,
  onDeleted,
}: {
  threads: ThreadSummary[];
  onDeleted: () => void;
}) {
  const router = useRouter();
  const [page, setPage] = useState(1);

  const pages = Math.max(1, Math.ceil(threads.length / PER_PAGE));
  // Clamped rather than corrected in an effect, so deleting the last row of the last
  // page falls back a page instead of rendering an empty one.
  const current = Math.min(page, pages);
  const start = (current - 1) * PER_PAGE;
  const visible = threads.slice(start, start + PER_PAGE);

  if (threads.length === 0) {
    return (
      <p className="text-[0.82rem]" style={{ color: "var(--text-faint)" }}>
        No traced threads yet. Start a conversation with{" "}
        <code className="mono">uv run main.py</code> and it will appear here.
      </p>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr
              className="text-[0.68rem] tracking-wide uppercase"
              style={{ background: "var(--surface-2)", color: "var(--text-faint)" }}
            >
              <Th className="w-12 text-right">#</Th>
              <Th className="w-36">Type</Th>
              <Th className="min-w-56">Summary</Th>
              <Th className="min-w-72">User query</Th>
              <Th className="w-20 text-center">Status</Th>
              <Th className="w-24 text-center">Escalated</Th>
              <Th className="w-44">Frustration</Th>
              <Th className="w-24 text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {visible.map((thread, index) => {
              const escalated = thread.escalations > 0;
              const closed = thread.status === "closed";
              const series = thread.frustration_series ?? [];
              const latest = series.length ? series[series.length - 1] : null;
              const href = `/threads/${encodeURIComponent(thread.thread_id)}`;

              return (
                <tr
                  key={thread.thread_id}
                  onClick={() => router.push(href)}
                  className="cursor-pointer border-t transition hover:bg-[var(--surface-2)]"
                  style={{ borderColor: "var(--border)" }}
                >
                  <Td className="text-right">
                    <span className="mono" style={{ color: "var(--text-faint)" }}>
                      {start + index + 1}
                    </span>
                  </Td>

                  <Td>
                    {thread.latest_category ? (
                      <span
                        className="chip"
                        style={{ background: "var(--jev-soft)", color: "var(--jev)" }}
                      >
                        {thread.latest_category}
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-faint)" }}>—</span>
                    )}
                  </Td>

                  <Td>
                    {/* The row handles the click, so anywhere in it opens the thread.
                        The real link stays for keyboard focus, middle-click and
                        "copy link address", which an onClick alone would lose. */}
                    <Link
                      href={href}
                      className="font-medium hover:underline"
                      style={closed ? { color: "var(--text-dim)" } : undefined}
                    >
                      {thread.title ?? (
                        <span className="mono">{thread.thread_id}</span>
                      )}
                    </Link>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      <span
                        className="mono text-[0.65rem]"
                        style={{ color: "var(--text-faint)" }}
                      >
                        {thread.customer_id} · {thread.turns} turn
                        {thread.turns === 1 ? "" : "s"} · {ago(thread.last_at)}
                      </span>
                      {thread.pending_approval && (
                        <span
                          className="chip"
                          style={{ background: "var(--review)", color: "var(--surface)" }}
                        >
                          waiting on you
                        </span>
                      )}
                    </div>
                  </Td>

                  <Td>
                    <p
                      className="line-clamp-2 text-[0.78rem] leading-snug"
                      style={{ color: "var(--text-dim)" }}
                    >
                      {thread.opening_message ?? "—"}
                    </p>
                  </Td>

                  <Td className="text-center">
                    <span
                      className="chip"
                      style={{
                        background: closed ? "var(--surface-2)" : "var(--allow-soft)",
                        color: closed ? "var(--text-faint)" : "var(--allow)",
                      }}
                    >
                      {closed ? "closed" : "open"}
                    </span>
                  </Td>

                  <Td className="text-center">
                    <span
                      className="chip"
                      style={{
                        background: escalated ? "var(--deny-soft)" : "var(--surface-2)",
                        color: escalated ? "var(--deny)" : "var(--text-faint)",
                      }}
                    >
                      {escalated ? "Yes" : "No"}
                    </span>
                  </Td>

                  <Td>
                    {series.length > 0 ? (
                      <div className="flex items-center gap-2">
                        <Sparkline values={series} threshold={1.5} />
                        <span className="mono" style={{ color: "var(--text-dim)" }}>
                          {latest!.toFixed(2)}
                        </span>
                      </div>
                    ) : (
                      <span style={{ color: "var(--text-faint)" }}>—</span>
                    )}
                  </Td>

                  <Td className="text-right">
                    <DeleteCell thread={thread} onDeleted={onDeleted} />
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div
          className="flex items-center gap-2 border-t px-3 py-2"
          style={{ borderColor: "var(--border)" }}
        >
          <span className="text-[0.7rem]" style={{ color: "var(--text-faint)" }}>
            {start + 1}–{Math.min(start + PER_PAGE, threads.length)} of {threads.length}
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            <PageButton disabled={current === 1} onClick={() => setPage(current - 1)}>
              ← Prev
            </PageButton>
            <span className="mono text-[0.72rem]" style={{ color: "var(--text-dim)" }}>
              {current} / {pages}
            </span>
            <PageButton disabled={current === pages} onClick={() => setPage(current + 1)}>
              Next →
            </PageButton>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Delete, behind a confirm that lives in the row.
 *
 * Deliberately not `window.confirm`: the row already says which thread this is, and the
 * second click lands in the same place as the first. Nothing is recoverable afterwards —
 * the trace, the title and the checkpoints all go — so the confirm is the whole safeguard.
 */
function DeleteCell({
  thread,
  onDeleted,
}: {
  thread: ThreadSummary;
  onDeleted: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await deleteThread(thread.thread_id);
      onDeleted();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
      setAsking(false);
    }
  }

  // The row navigates on click, so every control in here has to keep its click.
  const stop = (e: React.MouseEvent) => e.stopPropagation();

  if (error) {
    return (
      <span className="text-[0.68rem]" style={{ color: "var(--deny)" }} onClick={stop}>
        {error}
      </span>
    );
  }

  if (!asking) {
    return (
      <button
        onClick={(e) => {
          stop(e);
          setAsking(true);
        }}
        className="rounded px-2 py-1 text-[0.72rem] transition hover:underline"
        style={{ color: "var(--text-faint)" }}
        title={`Delete ${thread.thread_id}`}
      >
        Delete
      </button>
    );
  }

  return (
    <span className="flex items-center justify-end gap-1.5" onClick={stop}>
      <button
        onClick={(e) => {
          stop(e);
          void confirm();
        }}
        disabled={busy}
        className="rounded px-2 py-1 text-[0.72rem] font-semibold disabled:opacity-50"
        style={{ background: "var(--deny)", color: "var(--surface)" }}
      >
        {busy ? "…" : "Delete"}
      </button>
      <button
        onClick={(e) => {
          stop(e);
          setAsking(false);
        }}
        className="rounded px-2 py-1 text-[0.72rem]"
        style={{ color: "var(--text-dim)" }}
      >
        Cancel
      </button>
    </span>
  );
}

function PageButton({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rounded px-2 py-1 text-[0.72rem] transition disabled:opacity-35"
      style={{
        border: "1px solid var(--border-strong)",
        color: "var(--text-dim)",
      }}
    >
      {children}
    </button>
  );
}

function Th({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <th className={`px-3 py-2 font-semibold ${className}`}>{children}</th>;
}

function Td({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-3 py-2.5 align-top ${className}`}>{children}</td>;
}
