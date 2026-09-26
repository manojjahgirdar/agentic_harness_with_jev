"use client";

import { clockTime } from "@/lib/api";
import type { TraceEvent } from "@/lib/types";
import { ConfidenceBar, RubricMeter } from "./Meters";

const FRUSTRATION_LEVELS = ["calm", "frustrated", "angry"];
const RISK_LEVELS = ["routine", "notable", "severe"];

/** Colour and label per event type — the legend the whole timeline reads by. */
const STYLE: Record<
  string,
  { accent: string; soft: string; label: string }
> = {
  user_message: { accent: "var(--text-dim)", soft: "var(--surface-2)", label: "customer" },
  jev_triage: { accent: "var(--jev)", soft: "var(--jev-soft)", label: "Jev · triage" },
  jev_risk: { accent: "var(--jev)", soft: "var(--jev-soft)", label: "Jev · tool risk" },
  escalation_rule: { accent: "var(--review)", soft: "var(--review-soft)", label: "escalation rule" },
  skill_injected: { accent: "var(--route)", soft: "var(--route-soft)", label: "skill" },
  model_route: { accent: "var(--route)", soft: "var(--route-soft)", label: "model route" },
  policy: { accent: "var(--tool)", soft: "var(--tool-soft)", label: "policy" },
  hitl_request: { accent: "var(--review)", soft: "var(--review-soft)", label: "approval needed" },
  hitl_decision: { accent: "var(--human)", soft: "var(--human-soft)", label: "human decision" },
  tool_call: { accent: "var(--tool)", soft: "var(--tool-soft)", label: "tool" },
  agent_message: { accent: "var(--allow)", soft: "var(--allow-soft)", label: "agent" },
  human_message: { accent: "var(--human)", soft: "var(--human-soft)", label: "human agent" },
  thread_closed: { accent: "var(--text-dim)", soft: "var(--surface-2)", label: "closed" },
};

const VERDICT: Record<string, { accent: string; soft: string }> = {
  allow: { accent: "var(--allow)", soft: "var(--allow-soft)" },
  review: { accent: "var(--review)", soft: "var(--review-soft)" },
  deny: { accent: "var(--deny)", soft: "var(--deny-soft)" },
};

function num(d: Record<string, unknown>, k: string): number | undefined {
  const v = d[k];
  return typeof v === "number" ? v : undefined;
}
function str(d: Record<string, unknown>, k: string): string | undefined {
  const v = d[k];
  return typeof v === "string" ? v : undefined;
}

export function EventCard({ event }: { event: TraceEvent }) {
  const style = STYLE[event.event_type] ?? STYLE.tool_call;
  const d = event.detail ?? {};
  const isJev = event.event_type.startsWith("jev_");

  return (
    <div className="rail pb-3">
      <span
        className="node"
        style={{
          background: style.accent,
          ...(event.event_type === "hitl_request"
            ? { animation: "pulse-ring 1.9s ease-out infinite" }
            : {}),
        }}
      />
      <div
        className="card overflow-hidden"
        style={isJev ? { borderColor: "var(--jev)" } : undefined}
      >
        <div
          className="flex items-center gap-2 px-3 py-1.5"
          style={{ background: style.soft }}
        >
          <span
            className="chip"
            style={{ background: style.accent, color: "var(--surface)" }}
          >
            {style.label}
          </span>
          <span className="mono ml-auto" style={{ color: "var(--text-faint)" }}>
            {clockTime(event.ts)}
          </span>
        </div>

        <div className="px-3 py-2.5">
          <Body event={event} detail={d} />
        </div>
      </div>
    </div>
  );
}

function Body({
  event,
  detail: d,
}: {
  event: TraceEvent;
  detail: Record<string, unknown>;
}) {
  switch (event.event_type) {
    case "user_message":
    case "agent_message":
      return (
        <p className="text-[0.82rem] leading-relaxed whitespace-pre-wrap">
          {str(d, "text") ?? event.summary}
        </p>
      );

    case "human_message":
      return (
        <div className="space-y-1.5">
          <p className="text-[0.82rem] leading-relaxed whitespace-pre-wrap">
            {str(d, "text") ?? event.summary}
          </p>
          <p className="text-[0.7rem]" style={{ color: "var(--text-faint)" }}>
            sent by {str(d, "agent") ?? "support"} — the model did not write this
          </p>
        </div>
      );

    case "jev_triage": {
      const q = (d.questions ?? {}) as Record<string, string>;
      const conf = num(d, "category_confidence") ?? 0;
      return (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span
              className="chip"
              style={{ background: "var(--jev-soft)", color: "var(--jev)" }}
            >
              Choice → {str(d, "category")}
            </span>
            {conf < 0.6 && (
              <span
                className="chip"
                style={{ background: "var(--review-soft)", color: "var(--review)" }}
              >
                low confidence
              </span>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <ConfidenceBar
                value={conf}
                label="category confidence"
                threshold={0.6}
                thresholdLabel="below 0.60 → agent must confirm intent"
              />
              <Question text={q.category} />
            </div>
            <div>
              <ConfidenceBar
                value={num(d, "urgency") ?? 0}
                label="urgency (Noul)"
                threshold={0.7}
                thresholdLabel="≥ 0.70 counts as urgent"
              />
              <Question text={q.urgency} />
            </div>
            <div>
              <RubricMeter
                value={num(d, "frustration") ?? 0}
                levels={FRUSTRATION_LEVELS}
                label="frustration (Score)"
                threshold={1.5}
                thresholdLabel="≥ 1.50 counts as upset"
              />
              <Question text={q.frustration} />
            </div>
            <div>
              <ConfidenceBar
                value={num(d, "needs_reasoning") ?? 0}
                label="needs reasoning (Noul)"
                accent="var(--route)"
                threshold={0.5}
                thresholdLabel="≥ 0.50 → reasoning model"
              />
              <Question text={q.needs_reasoning} />
            </div>
          </div>
        </div>
      );
    }

    case "jev_risk":
      return (
        <div className="space-y-2">
          <RubricMeter
            value={num(d, "risk_score") ?? 0}
            levels={RISK_LEVELS}
            label={`risk of ${str(d, "tool")} running unsupervised`}
            threshold={num(d, "threshold") ?? 1.5}
            thresholdLabel={`≥ ${(num(d, "threshold") ?? 1.5).toFixed(2)} → human review`}
          />
          <Question text={str(d, "question")} />
          <Verdict
            ok={!d.needs_review}
            okText="auto-approved"
            badText="sent for human review"
          />
        </div>
      );

    case "model_route":
      return (
        <div className="flex flex-wrap items-center gap-2">
          <span
            className="chip"
            style={{ background: "var(--route)", color: "var(--surface)" }}
          >
            {str(d, "model")}
          </span>
          <span className="text-[0.78rem]" style={{ color: "var(--text-dim)" }}>
            {str(d, "reason")}
          </span>
        </div>
      );

    case "escalation_rule":
      return (
        <div className="space-y-2">
          <p className="text-[0.82rem]">{event.summary}</p>
          {Array.isArray(d.frustration_history) && (
            <p className="mono" style={{ color: "var(--text-faint)" }}>
              frustration so far:{" "}
              {(d.frustration_history as number[])
                .map((f) => f.toFixed(2))
                .join(" → ")}
              {d.frustration_sustained ? "  · sustained" : ""}
            </p>
          )}
          {typeof d.cancel_unlocked_order === "string" && d.cancel_unlocked_order && (
            <span
              className="chip"
              style={{ background: "var(--allow-soft)", color: "var(--allow)" }}
            >
              cancellation unlocked for {d.cancel_unlocked_order}
            </span>
          )}
        </div>
      );

    case "skill_injected":
      return (
        <p className="text-[0.8rem]" style={{ color: "var(--text-dim)" }}>
          Loaded <strong style={{ color: "var(--text)" }}>{str(d, "category")}</strong>
          /SKILL.md into the system prompt
          {d.escalation_directive ? ", plus the escalation directive" : ""}.
        </p>
      );

    case "policy": {
      const verdict = str(d, "verdict") ?? "allow";
      const v = VERDICT[verdict] ?? VERDICT.allow;
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="chip"
              style={{ background: v.accent, color: "var(--surface)" }}
            >
              {verdict}
            </span>
            <span className="mono">{str(d, "tool")}</span>
          </div>
          <p className="text-[0.8rem]" style={{ color: "var(--text-dim)" }}>
            {str(d, "reason")}
          </p>
          <Facts
            items={[
              ["stage", str(d, "stage")],
              ["order total", money(num(d, "order_total"))],
              ["refund", money(num(d, "refund_amount") ?? num(d, "amount"))],
              ["auto limit", money(num(d, "auto_limit"))],
              ["hard ceiling", money(num(d, "hard_ceiling"))],
              [
                "refunds in window",
                num(d, "recent_refund_count") !== undefined
                  ? String(num(d, "recent_refund_count"))
                  : undefined,
              ],
              ["remedy first", d.remedy_first ? "yes" : undefined],
            ]}
          />
        </div>
      );
    }

    case "hitl_request":
      return (
        <div className="space-y-2">
          <p className="text-[0.82rem] font-medium">{event.summary}</p>
          <p className="text-[0.75rem]" style={{ color: "var(--text-dim)" }}>
            triggered by {str(d, "trigger")}
          </p>
          <Args args={d.args as Record<string, unknown> | undefined} />
        </div>
      );

    case "hitl_decision": {
      const choice = str(d, "decision") ?? "approve";
      const v =
        choice === "reject"
          ? VERDICT.deny
          : choice === "edit"
            ? VERDICT.review
            : VERDICT.allow;
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="chip"
              style={{ background: v.accent, color: "var(--surface)" }}
            >
              {choice}
            </span>
            <span className="mono">{str(d, "tool")}</span>
            <span className="text-[0.72rem]" style={{ color: "var(--text-faint)" }}>
              by {str(d, "reviewer") ?? "reviewer"} · {str(d, "source") ?? "cli"}
            </span>
          </div>
          {str(d, "message") && (
            <p className="text-[0.8rem]" style={{ color: "var(--text-dim)" }}>
              “{str(d, "message")}”
            </p>
          )}
          {d.edited_args != null && (
            <div className="grid gap-2 sm:grid-cols-2">
              <Args args={d.original_args as Record<string, unknown>} title="proposed" />
              <Args args={d.edited_args as Record<string, unknown>} title="executed" />
            </div>
          )}
        </div>
      );
    }

    case "tool_call": {
      const failed = str(d, "status") === "error";
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="chip"
              style={{
                background: failed ? "var(--deny)" : "var(--tool)",
                color: "var(--surface)",
              }}
            >
              {str(d, "tool")}
            </span>
            {failed && (
              <span className="text-[0.72rem]" style={{ color: "var(--deny)" }}>
                refused by policy
              </span>
            )}
          </div>
          <Args args={d.args as Record<string, unknown> | undefined} />
          <details>
            <summary
              className="text-[0.72rem] hover:underline"
              style={{ color: "var(--text-faint)" }}
            >
              result
            </summary>
            <pre
              className="mono mt-1 max-h-56 overflow-auto rounded p-2 whitespace-pre-wrap"
              style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}
            >
              {str(d, "result")}
            </pre>
          </details>
        </div>
      );
    }

    default:
      return <p className="text-[0.82rem]">{event.summary}</p>;
  }
}

function Question({ text }: { text?: string }) {
  if (!text) return null;
  return (
    <p className="mt-1 text-[0.62rem] italic" style={{ color: "var(--text-faint)" }}>
      {text}
    </p>
  );
}

function Verdict({
  ok,
  okText,
  badText,
}: {
  ok: boolean;
  okText: string;
  badText: string;
}) {
  return (
    <span
      className="chip"
      style={{
        background: ok ? "var(--allow-soft)" : "var(--review-soft)",
        color: ok ? "var(--allow)" : "var(--review)",
      }}
    >
      {ok ? okText : badText}
    </span>
  );
}

function money(v?: number) {
  return v === undefined ? undefined : `$${v.toFixed(2)}`;
}

function Facts({ items }: { items: [string, string | undefined][] }) {
  const shown = items.filter(([, v]) => v !== undefined);
  if (!shown.length) return null;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {shown.map(([k, v]) => (
        <span key={k} className="mono" style={{ color: "var(--text-faint)" }}>
          {k} <strong style={{ color: "var(--text-dim)" }}>{v}</strong>
        </span>
      ))}
    </div>
  );
}

function Args({
  args,
  title,
}: {
  args?: Record<string, unknown>;
  title?: string;
}) {
  if (!args || !Object.keys(args).length) return null;
  return (
    <div>
      {title && (
        <div className="mb-1 text-[0.62rem] uppercase tracking-wide" style={{ color: "var(--text-faint)" }}>
          {title}
        </div>
      )}
      <div
        className="mono rounded p-2"
        style={{ background: "var(--surface-2)" }}
      >
        {Object.entries(args).map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <span style={{ color: "var(--text-faint)" }}>{k}</span>
            <span className="min-w-0 flex-1 break-words" style={{ color: "var(--text-dim)" }}>
              {typeof v === "string" ? v : JSON.stringify(v)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
