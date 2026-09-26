"use client";

import Link from "next/link";
import { ago } from "@/lib/api";
import type { ThreadSummary } from "@/lib/types";
import { Sparkline } from "./Meters";

/**
 * Threads to look at before they become escalations.
 *
 * The flag comes from the API, not from a number compared in the browser: the threshold
 * is a policy knob and lives with the others in `src/config.py`. Frustration past that
 * line is the whole rule — a thread that went badly and then went quiet is still someone
 * left unhappy, so it stays here and is simply no longer marked live.
 *
 * It renders nothing when nothing qualifies. A permanent empty "needs attention" panel
 * teaches people to stop looking at it.
 */
export function AttentionStrip({
  threads,
  threshold,
}: {
  threads: ThreadSummary[];
  threshold: number;
}) {
  if (threads.length === 0) return null;

  const live = threads.filter((t) => t.is_live).length;

  return (
    <section className="mb-6">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-2">
        <h2 className="text-sm font-semibold" style={{ color: "var(--review)" }}>
          Action maybe required soon
        </h2>
        <span className="text-[0.72rem]" style={{ color: "var(--text-faint)" }}>
          {threads.length} thread{threads.length === 1 ? "" : "s"} past{" "}
          {threshold.toFixed(2)} frustration
          {live > 0 && <span style={{ color: "var(--allow)" }}> · {live} live</span>}
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {threads.map((thread) => {
          const series = thread.frustration_series ?? [];
          const latest = series[series.length - 1] ?? 0;

          return (
            <Link
              key={thread.thread_id}
              href={`/threads/${encodeURIComponent(thread.thread_id)}`}
              className="card block p-3 transition hover:border-[var(--review)]"
              style={{ borderColor: "var(--review-soft)" }}
            >
              <div className="flex items-center gap-2">
                {thread.is_live && (
                  <span
                    className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ background: "var(--allow)" }}
                    title="Still moving"
                  />
                )}
                <span className="truncate text-[0.82rem] font-medium">
                  {thread.title ?? thread.thread_id}
                </span>
                {thread.pending_approval && (
                  <span
                    className="chip ml-auto shrink-0"
                    style={{ background: "var(--review)", color: "var(--surface)" }}
                  >
                    waiting on you
                  </span>
                )}
              </div>

              <p
                className="mt-0.5 line-clamp-1 text-[0.72rem]"
                style={{ color: "var(--text-dim)" }}
              >
                {thread.opening_message}
              </p>

              <div className="mt-2 flex items-center gap-2">
                <Sparkline values={series} threshold={1.5} />
                <span className="mono font-semibold" style={{ color: "var(--review)" }}>
                  {latest.toFixed(2)}
                </span>
                <span
                  className="mono ml-auto text-[0.65rem]"
                  style={{ color: "var(--text-faint)" }}
                >
                  {thread.customer_id} · {ago(thread.last_at)}
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
