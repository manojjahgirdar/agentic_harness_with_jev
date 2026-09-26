"use client";

import { useMemo, useState } from "react";
import type { ThreadDetail } from "@/lib/types";
import { ApprovalPanel } from "./ApprovalPanel";
import { EventCard } from "./EventCard";
import { HumanReply } from "./HumanReply";
import { StatusControl } from "./StatusControl";
import { Sparkline } from "./Meters";

const JEV_ONLY = new Set(["jev_triage", "jev_risk"]);

export function TraceView({
  detail,
  onResolved,
}: {
  detail: ThreadDetail;
  onResolved: () => void;
}) {
  const [jevOnly, setJevOnly] = useState(false);
  const state = detail.state ?? {};
  const history = state.frustration_history ?? [];

  const turns = useMemo(
    () =>
      detail.turns
        .map((t) => ({
          ...t,
          events: jevOnly
            ? t.events.filter((e) => JEV_ONLY.has(e.event_type))
            : t.events,
        }))
        .filter((t) => t.events.length > 0),
    [detail.turns, jevOnly],
  );

  const jevCount = detail.events.filter((e) => JEV_ONLY.has(e.event_type)).length;

  return (
    <div className="card min-w-0 overflow-hidden">
      <header
        className="border-b px-4 py-3 lg:px-5"
        style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h2 className={`text-sm font-semibold${detail.title ? "" : " mono"}`}>
            {detail.title ?? detail.thread_id}
          </h2>
          <span
            className="chip"
            style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}
          >
            {detail.customer_id}
          </span>
          {detail.title && (
            <span
              className="chip mono"
              style={{ background: "var(--surface-2)", color: "var(--text-faint)" }}
              title="Resume this thread with --thread"
            >
              {detail.thread_id}
            </span>
          )}
          <span className="text-[0.7rem]" style={{ color: "var(--text-faint)" }}>
            {detail.events.length} events · {jevCount} Jev call
            {jevCount === 1 ? "" : "s"}
          </span>

          <span className="ml-auto">
            <StatusControl
              threadId={detail.thread_id}
              status={detail.status}
              onChanged={onResolved}
            />
          </span>

          <label
            className="flex cursor-pointer items-center gap-1.5 text-[0.72rem]"
            style={{ color: "var(--text-dim)" }}
          >
            <input
              type="checkbox"
              checked={jevOnly}
              onChange={(e) => setJevOnly(e.target.checked)}
              className="accent-[var(--jev)]"
            />
            Jev decisions only
          </label>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-2">
          {history.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-[0.68rem]" style={{ color: "var(--text-faint)" }}>
                frustration
              </span>
              <Sparkline values={history} threshold={1.5} />
              <span className="mono" style={{ color: "var(--text-dim)" }}>
                {history[history.length - 1].toFixed(2)}/2
              </span>
            </div>
          )}
          {state.frustration_sustained && (
            <Flag tone="deny">sustained — cancellation unlocked</Flag>
          )}
          {state.escalation_required && <Flag tone="review">escalated</Flag>}
          {state.cancel_unlocked_order && (
            <Flag tone="allow">{state.cancel_unlocked_order} cancellable</Flag>
          )}
        </div>

        {state.escalation_note && (
          <p
            className="mt-2 rounded px-2.5 py-1.5 text-[0.75rem]"
            style={{ background: "var(--review-soft)", color: "var(--review)" }}
          >
            {state.escalation_note}
          </p>
        )}
      </header>

      <div className="px-4 py-4 lg:px-5">
        {detail.pending && (
          <ApprovalPanel
            threadId={detail.thread_id}
            pending={detail.pending}
            onResolved={onResolved}
          />
        )}

        {state.escalation_required && detail.status.status === "open" && (
          <HumanReply
            threadId={detail.thread_id}
            note={state.escalation_note}
            blocked={detail.pending !== null}
            onSent={onResolved}
          />
        )}

        {turns.map(({ turn, events }) => (
          <section key={turn} className="mb-5">
            <div className="mb-2 flex items-center gap-2">
              <span
                className="chip"
                style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}
              >
                turn {turn}
              </span>
              <span
                className="h-px flex-1"
                style={{ background: "var(--border)" }}
              />
            </div>
            {events.map((event) => (
              <EventCard key={event.id} event={event} />
            ))}
          </section>
        ))}

        {turns.length === 0 && (
          <p className="text-[0.8rem]" style={{ color: "var(--text-faint)" }}>
            No Jev decisions in this thread yet.
          </p>
        )}
      </div>
    </div>
  );
}

function Flag({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone: "allow" | "deny" | "review";
}) {
  return (
    <span
      className="chip"
      style={{ background: `var(--${tone}-soft)`, color: `var(--${tone})` }}
    >
      {children}
    </span>
  );
}
