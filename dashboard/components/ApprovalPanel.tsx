"use client";

import { useMemo, useState } from "react";
import { resumeThread } from "@/lib/api";
import type { ActionRequest, Decision, Pending } from "@/lib/types";

/**
 * Resolves a paused approval.
 *
 * The graph is genuinely suspended at a checkpoint while this is open, so whatever is
 * chosen here is what the tool executes — an edited amount is re-checked by the policy
 * layer before it runs, which is why a raised figure can still come back refused.
 */
export function ApprovalPanel({
  threadId,
  pending,
  onResolved,
}: {
  threadId: string;
  pending: Pending;
  onResolved: () => void;
}) {
  const action = pending.action_requests[0];
  const allowed =
    pending.review_configs[0]?.allowed_decisions ?? ["approve", "reject"];

  const [mode, setMode] = useState<"idle" | "edit" | "reject">("idle");
  const [showDetails, setShowDetails] = useState(false);
  const [args, setArgs] = useState<Record<string, unknown>>(action.args);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(decision: Decision) {
    setBusy(true);
    setError(null);
    try {
      await resumeThread(threadId, [decision]);
      setMode("idle");
      onResolved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="card pulse mb-4 overflow-hidden"
      style={{ borderColor: "var(--review)" }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2"
        style={{ background: "var(--review-soft)" }}
      >
        <span
          className="chip"
          style={{ background: "var(--review)", color: "var(--surface)" }}
        >
          waiting on you
        </span>
        <span className="mono font-semibold">{action.name}</span>
      </div>

      <div className="space-y-3 p-3">
        <Brief action={action} open={showDetails} onToggle={setShowDetails} />

        {mode === "edit" ? (
          <div className="space-y-2">
            {Object.entries(args).map(([key, value]) => (
              <label key={key} className="block">
                <span
                  className="mono mb-0.5 block"
                  style={{ color: "var(--text-faint)" }}
                >
                  {key}
                </span>
                <input
                  className="mono w-full rounded px-2 py-1.5 outline-none"
                  style={{
                    background: "var(--surface-2)",
                    border: "1px solid var(--border-strong)",
                    color: "var(--text)",
                  }}
                  value={String(value ?? "")}
                  onChange={(e) => {
                    const raw = e.target.value;
                    const next =
                      typeof value === "number" && raw !== "" && !isNaN(Number(raw))
                        ? Number(raw)
                        : raw;
                    setArgs({ ...args, [key]: next });
                  }}
                />
              </label>
            ))}
            <div className="flex gap-2">
              <Button
                tone="review"
                busy={busy}
                onClick={() =>
                  send({ type: "edit", args, tool_name: action.name })
                }
              >
                Run edited
              </Button>
              <Button tone="ghost" onClick={() => setMode("idle")}>
                Cancel
              </Button>
            </div>
          </div>
        ) : mode === "reject" ? (
          <div className="space-y-2">
            <textarea
              className="w-full rounded px-2 py-1.5 text-[0.8rem] outline-none"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border-strong)",
                color: "var(--text)",
              }}
              rows={2}
              placeholder="Why are you declining? The agent is told this."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <div className="flex gap-2">
              <Button
                tone="deny"
                busy={busy}
                onClick={() =>
                  send({ type: "reject", message: reason || undefined })
                }
              >
                Confirm reject
              </Button>
              <Button tone="ghost" onClick={() => setMode("idle")}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {allowed.includes("approve") && (
              <Button
                tone="allow"
                busy={busy}
                onClick={() => send({ type: "approve" })}
              >
                Approve
              </Button>
            )}
            {allowed.includes("edit") && (
              <Button tone="review" onClick={() => setMode("edit")}>
                Edit…
              </Button>
            )}
            {allowed.includes("reject") && (
              <Button tone="deny" onClick={() => setMode("reject")}>
                Reject
              </Button>
            )}
          </div>
        )}

        {error && (
          <p className="text-[0.75rem]" style={{ color: "var(--deny)" }}>
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * The reviewer's headline: who, how much, and the one-line why.
 *
 * The tool's `description` is written for the CLI, where a reviewer has nothing but the
 * text — several labelled lines of order stage, frustration trend and policy ceiling. In
 * the dashboard most of that is already on screen (the header carries the sparkline and
 * the flags), so it collapses to a summary and the untouched original sits behind the
 * toggle for anyone who wants the whole thing before they approve.
 */
function Brief({
  action,
  open,
  onToggle,
}: {
  action: ActionRequest;
  open: boolean;
  onToggle: (next: boolean) => void;
}) {
  const { headline, why } = useMemo(
    () => summarize(action.description),
    [action.description],
  );
  const chips = useMemo(() => argChips(action.args), [action.args]);

  if (!action.description && chips.length === 0) return null;

  return (
    <div className="space-y-2">
      {headline && <p className="text-[0.85rem] font-semibold">{headline}</p>}

      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map((chip) => (
            <span
              key={chip}
              className="chip mono"
              style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}
            >
              {chip}
            </span>
          ))}
        </div>
      )}

      {why && (
        <p
          className="line-clamp-2 text-[0.78rem]"
          style={{ color: "var(--text-dim)" }}
        >
          {why}
        </p>
      )}

      {action.description && (
        <button
          onClick={() => onToggle(!open)}
          className="text-[0.72rem] font-semibold underline decoration-dotted underline-offset-2"
          style={{ color: "var(--text-faint)" }}
        >
          {open ? "Hide details" : "View details"}
        </button>
      )}

      {open && action.description && (
        <pre
          className="mono rounded p-2 whitespace-pre-wrap"
          style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}
        >
          {action.description}
          {"\n\n"}
          {JSON.stringify(action.args, null, 2)}
        </pre>
      )}
    </div>
  );
}

/** First line as the headline, and the most decision-relevant `Label: value` as the why. */
function summarize(description?: string): { headline: string; why: string } {
  const lines = (description ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return { headline: "", why: "" };

  const fields = new Map<string, string>();
  for (const line of lines.slice(1)) {
    const split = line.indexOf(": ");
    if (split > 0) fields.set(line.slice(0, split).toLowerCase(), line.slice(split + 2));
  }

  const why =
    fields.get("reason") ??
    fields.get("reason given") ??
    fields.get("why this stopped") ??
    "";

  return { headline: lines[0], why };
}

/** The args that fit on a chip — `reason` is prose and already shown as the why. */
function argChips(args: Record<string, unknown>): string[] {
  const chips: string[] = [];
  for (const [key, value] of Object.entries(args)) {
    if (key === "reason" || value === null || value === undefined || value === "") continue;
    if (key === "amount" && typeof value === "number") chips.push(`$${value.toFixed(2)}`);
    else if (key === "valid_days") chips.push(`valid ${value} days`);
    else if (typeof value === "object") continue;
    else chips.push(String(value));
  }
  return chips;
}

function Button({
  children,
  onClick,
  tone,
  busy,
}: {
  children: React.ReactNode;
  onClick: () => void;
  tone: "allow" | "deny" | "review" | "ghost";
  busy?: boolean;
}) {
  const filled = tone !== "ghost";
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className="rounded px-3 py-1.5 text-[0.78rem] font-semibold transition disabled:opacity-50"
      style={{
        background: filled ? `var(--${tone})` : "transparent",
        color: filled ? "var(--surface)" : "var(--text-dim)",
        border: filled ? "none" : "1px solid var(--border-strong)",
      }}
    >
      {busy ? "working…" : children}
    </button>
  );
}
