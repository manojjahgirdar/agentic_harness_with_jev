"use client";

import { useState } from "react";
import { sendHumanReply } from "@/lib/api";

/**
 * Take the conversation over from the agent.
 *
 * Only offered on an escalated thread, where the model has already been told to hand
 * off: what is typed here goes straight into the transcript the agent reads, so the
 * model sees on its next turn what a person already promised. It does not run the
 * model — nobody is drafting on the human's behalf.
 */
export function HumanReply({
  threadId,
  note,
  blocked,
  onSent,
}: {
  threadId: string;
  note?: string;
  blocked: boolean;
  onSent: () => void;
}) {
  const [text, setText] = useState("");
  const [agent, setAgent] = useState("support");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    const body = text.trim();
    if (!body || busy) return;
    setBusy(true);
    setError(null);
    try {
      await sendHumanReply(threadId, body, agent.trim() || "support");
      setText("");
      onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card mb-4 overflow-hidden" style={{ borderColor: "var(--human)" }}>
      <div
        className="flex flex-wrap items-center gap-2 px-3 py-2"
        style={{ background: "var(--human-soft)" }}
      >
        <span
          className="chip"
          style={{ background: "var(--human)", color: "var(--surface)" }}
        >
          escalated — reply as support
        </span>
        {note && (
          <span className="text-[0.72rem]" style={{ color: "var(--text-dim)" }}>
            {note}
          </span>
        )}
      </div>

      <div className="space-y-2 p-3">
        <textarea
          className="w-full rounded px-2 py-1.5 text-[0.8rem] outline-none"
          style={{
            background: "var(--surface-2)",
            border: "1px solid var(--border-strong)",
            color: "var(--text)",
          }}
          rows={3}
          disabled={blocked}
          placeholder={
            blocked
              ? "Resolve the approval above before replying."
              : "Write to the customer. This goes into the thread as support, and the agent reads it on the next turn."
          }
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void send();
          }}
        />

        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5">
            <span className="text-[0.72rem]" style={{ color: "var(--text-faint)" }}>
              as
            </span>
            <input
              className="mono w-28 rounded px-2 py-1 text-[0.75rem] outline-none"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border-strong)",
                color: "var(--text)",
              }}
              value={agent}
              disabled={blocked}
              onChange={(e) => setAgent(e.target.value)}
            />
          </label>

          <button
            onClick={() => void send()}
            disabled={busy || blocked || !text.trim()}
            className="rounded px-3 py-1.5 text-[0.78rem] font-semibold transition disabled:opacity-40"
            style={{ background: "var(--human)", color: "var(--surface)" }}
          >
            {busy ? "sending…" : "Send to customer"}
          </button>

          <span className="text-[0.7rem]" style={{ color: "var(--text-faint)" }}>
            ⌘↵ to send
          </span>
        </div>

        {error && (
          <p className="text-[0.75rem]" style={{ color: "var(--deny)" }}>
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
