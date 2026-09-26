export type EventType =
  | "user_message"
  | "jev_triage"
  | "escalation_rule"
  | "skill_injected"
  | "model_route"
  | "jev_risk"
  | "policy"
  | "hitl_request"
  | "hitl_decision"
  | "tool_call"
  | "agent_message"
  | "human_message"
  | "thread_closed";

export interface TraceEvent {
  id: number;
  thread_id: string;
  customer_id: string;
  turn: number;
  ts: string;
  event_type: EventType;
  summary: string;
  detail: Record<string, unknown>;
}

export interface ThreadSummary {
  thread_id: string;
  customer_id: string;
  /** What the customer wanted, in a few words. Null until the titler has run. */
  title: string | null;
  events: number;
  turns: number;
  started_at: string;
  last_at: string;
  last_id: number;
  opening_message: string | null;
  latest_category: string | null;
  latest_frustration: number | null;
  /** Every frustration score Jev gave this thread, oldest first. */
  frustration_series: number[];
  escalations: number;
  approvals: number;
  pending_approval: boolean;
  /** Which tool the pending approval is for, when one is pending. */
  pending_tool: string | null;
  escalation_required: boolean;
  /** Escalated, and no human has replied since the customer last wrote. */
  awaiting_human: boolean;
  /** Frustration is over the watchlist threshold. */
  needs_attention: boolean;
  /** Moved recently enough to still be in play. */
  is_live: boolean;
  status: "open" | "closed";
}

export interface CustomerGroup {
  customer_id: string;
  threads: ThreadSummary[];
  thread_count: number;
  last_at: string;
  pending_approvals: number;
}

export interface ActionRequest {
  name: string;
  args: Record<string, unknown>;
  description?: string;
}

export interface Pending {
  interrupt_id: string | null;
  action_requests: ActionRequest[];
  review_configs: { action_name: string; allowed_decisions: string[] }[];
}

export interface ThreadState {
  triage?: Record<string, number | string> | null;
  frustration_history?: number[];
  frustration_sustained?: boolean;
  escalation_required?: boolean;
  escalation_note?: string;
  cancel_unlocked_order?: string | null;
  message_count?: number;
}

export interface ThreadStatus {
  status: "open" | "closed";
  closed_by: string | null;
  reason: string | null;
  updated_at: string | null;
}

export interface ThreadDetail {
  thread_id: string;
  customer_id: string;
  title: string | null;
  status: ThreadStatus;
  events: TraceEvent[];
  turns: { turn: number; events: TraceEvent[] }[];
  pending: Pending | null;
  state: ThreadState;
}

export interface Decision {
  type: "approve" | "reject" | "edit";
  message?: string;
  args?: Record<string, unknown>;
  tool_name?: string;
}
