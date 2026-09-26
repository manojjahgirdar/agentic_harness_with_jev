"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { getThread } from "@/lib/api";
import type { ThreadDetail } from "@/lib/types";
import { useTraceStream } from "@/lib/useTraceStream";
import { TraceView } from "@/components/TraceView";

/**
 * One thread, on its own page.
 *
 * A route rather than a selection in a split view: the trace is the thing being read,
 * so it gets the width, and the URL is what you send someone when an approval needs a
 * second opinion.
 */
export default function ThreadPage({
  params,
}: {
  params: Promise<{ threadId: string }>;
}) {
  const { threadId } = use(params);
  const id = decodeURIComponent(threadId);

  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDetail(await getThread(id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useTraceStream((threads) => {
    if (threads.includes(id)) void refresh();
  });

  return (
    <main className="mx-auto min-h-dvh w-full max-w-5xl px-6 pt-10 pb-16 lg:px-10">
      <Link
        href="/"
        className="mb-4 inline-block text-[0.75rem] hover:underline"
        style={{ color: "var(--text-dim)" }}
      >
        ← All threads
      </Link>

      {error && (
        <p className="card p-4 text-[0.8rem]" style={{ color: "var(--deny)" }}>
          {error}
        </p>
      )}

      {detail && <TraceView detail={detail} onResolved={refresh} />}

      {!detail && !error && (
        <p className="text-[0.8rem]" style={{ color: "var(--text-faint)" }}>
          Loading {id}…
        </p>
      )}
    </main>
  );
}
