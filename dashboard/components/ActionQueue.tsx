"use client";

import Link from "next/link";
import { ago } from "@/lib/api";
import type { ThreadSummary } from "@/lib/types";

export type ActionItem = {
  thread: ThreadSummary;
  kind: "approval" | "escalation";
};

/**
 * Work that is actually blocked on a person.
 *
 * Two kinds, and the difference is worth keeping visible. An **approval** means the graph
 * is suspended mid-turn: the tool has not run, the customer has had no answer, and
 * nothing moves until someone decides — so these sort first. An **escalation** means the
 * agent handed off and said so to the customer; the conversation is not frozen, but a
 * promise has been made that only a person can keep.
 *
 * Everything here is a thread someone has to open. The strip below it is the softer
 * question of what might need attention next.
 */
export function ActionQueue({ items }: { items: ActionItem[] }) {
  if (items.length === 0) return null;

  return (
    <section className="mb-6">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-2">
        <h2 className="text-sm font-semibold" style={{ color: "var(--deny)" }}>
          Action required
        </h2>
        <span className="text-[0.72rem]" style={{ color: "var(--text-faint)" }}>
          {items.length} thread{items.length === 1 ? "" : "s"} blocked on a human
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {items.map(({ thread, kind }) => {
          const approval = kind === "approval";
          const accent = approval ? "var(--review)" : "var(--human)";

          return (
            <Link
              key={`${thread.thread_id}:${kind}`}
              href={`/threads/${encodeURIComponent(thread.thread_id)}`}
              className="card block p-3 transition"
              style={{ borderColor: accent }}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className="chip"
                  style={{ background: accent, color: "var(--surface)" }}
                >
                  {approval ? "approval" : "escalation"}
                </span>
                <span className="truncate text-[0.82rem] font-medium">
                  {thread.title ?? thread.thread_id}
                </span>
              </div>

              <p className="mt-1.5 text-[0.75rem]" style={{ color: "var(--text-dim)" }}>
                {approval ? (
                  <>
                    <span className="mono">{thread.pending_tool ?? "a tool call"}</span>{" "}
                    is paused — approve, edit or reject it
                  </>
                ) : (
                  <>Handed to a human, and nobody has replied yet</>
                )}
              </p>

              <p
                className="mono mt-2 text-[0.65rem]"
                style={{ color: "var(--text-faint)" }}
              >
                {thread.customer_id} · {ago(thread.last_at)}
              </p>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
