"""Terminal front end for the support agent -- the customer's side of the conversation.

Deliberately thin: it owns input and output, and nothing else. Approvals are not its job
any more. Every paused tool call is resolved in the dashboard, so when the graph
interrupts, this process waits rather than prompting; a human agent watching an escalated
thread there can also reply into it, and those replies are printed here.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any

from langchain_core.messages import AIMessage

import time

from src.agents.agent import build_support_agent
from src.context import SupportContext
from src.db.database import init_db
from src.trace import HUMAN_AGENT_KEY

BANNER = """\
Tiffin support agent
  customer : {customer}
  thread   : {thread}
  approvals: resolved in the dashboard — http://localhost:3000
  commands : /quit  /new  /state  (empty line checks for a human agent's reply)
"""


def _print_reply(result: dict[str, Any]) -> None:
    """Print the model's reply -- skipping a human agent's, which `_drain_human_replies`
    has already shown under its author's name."""
    for message in reversed(result.get("messages", [])):
        if not isinstance(message, AIMessage) or not message.text:
            continue
        if (message.additional_kwargs or {}).get(HUMAN_AGENT_KEY):
            continue
        print(f"\nagent: {message.text}\n")
        return
    print("\nagent: (no reply)\n")


def _drain_human_replies(
    agent, config: dict[str, Any], seen: set[str]
) -> None:
    """Print anything a human agent has said into this thread from the dashboard.

    An escalated thread can be answered by a person, who writes into the same checkpoint
    this process reads. Their messages therefore arrive without a turn of their own, so
    they are drained on either side of `input()` rather than printed by `_print_reply`:
    once after the agent replies, and once before the next prompt, which is why pressing
    enter on an empty line is a way to check for one.
    """
    try:
        messages = (agent.get_state(config).values or {}).get("messages", [])
    except Exception:  # noqa: BLE001 - a new thread has no checkpoint yet
        return

    for message in messages:
        author = (getattr(message, "additional_kwargs", None) or {}).get(HUMAN_AGENT_KEY)
        key = getattr(message, "id", None)
        if not author or not key or key in seen:
            continue
        seen.add(key)
        print(f"\n{author} (human): {message.text}\n")


def _wait_for_dashboard(
    agent, config: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    """Block until the dashboard resolves this approval *and* the turn finishes.

    Only one process may resolve a given interrupt: whoever calls `Command(resume=...)`
    first advances the checkpoint, and a second resume would be applied to a graph that
    has already moved on. Approvals belong to the dashboard, so this process never
    prompts -- it watches the checkpoint and picks the conversation back up afterwards.

    Waiting for the interrupt to clear is not enough. It clears the moment the other
    process *starts* resuming, while the model is still working, so reading the state
    then returns a transcript with no reply in it yet. The turn is only done when the
    graph also has no next step queued.
    """
    names = ", ".join(a["name"] for a in request["action_requests"])
    print(f"\n  ⏸  {names} is waiting for approval in the dashboard.")
    print("     http://localhost:3000 — Ctrl-C to stop waiting.\n")

    announced = False
    while True:
        time.sleep(0.5)
        snapshot = agent.get_state(config)
        still_pending = any(
            isinstance(i.value, dict) and "action_requests" in i.value
            for i in (snapshot.interrupts or ())
        )
        if still_pending:
            continue
        if not announced:
            print("  ✓  resolved in the dashboard, finishing the turn…")
            announced = True
        if not snapshot.next:
            print()
            return snapshot.values or {}


def run_turn(
    agent,
    payload: Any,
    config: dict[str, Any],
    context: SupportContext,
) -> dict[str, Any]:
    """Invoke the agent, waiting out any approval interrupts until the turn finishes.

    `context` is a separate `invoke` kwarg rather than a config key -- middleware and
    tools read it as `runtime.context`.
    """
    result = agent.invoke(payload, config=config, context=context)

    while result.get("__interrupt__"):
        result = _wait_for_dashboard(agent, config, result["__interrupt__"][0].value)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Tiffin customer support agent")
    parser.add_argument(
        "--customer",
        default="cust-1",
        help="Authenticated customer. Seeded: cust-1, cust-2, cust-7 (refund abuser).",
    )
    parser.add_argument(
        "--thread",
        default=None,
        help="Thread ID to resume. Omit to start a new one.",
    )
    parser.add_argument(
        "--reseed", action="store_true", help="Reset the demo orders and refunds."
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Hide routing and policy decisions."
    )
    args = parser.parse_args()

    init_db(reseed=args.reseed)

    thread_id = args.thread or f"thread-{uuid.uuid4().hex[:8]}"
    agent = build_support_agent(verbose=not args.quiet)

    context = SupportContext(customer_id=args.customer)
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 50,
    }

    print(BANNER.format(customer=args.customer, thread=thread_id))

    seen: set[str] = set()
    while True:
        _drain_human_replies(agent, config, seen)
        try:
            text = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not text:
            continue
        if text in {"/quit", "/exit"}:
            return
        if text == "/new":
            thread_id = f"thread-{uuid.uuid4().hex[:8]}"
            config["configurable"]["thread_id"] = thread_id
            seen.clear()
            print(f"  started {thread_id}\n")
            continue
        if text == "/state":
            snapshot = agent.get_state(config).values
            print(
                json.dumps(
                    {
                        "triage": snapshot.get("triage"),
                        "escalation_required": snapshot.get("escalation_required"),
                        "escalation_note": snapshot.get("escalation_note"),
                        "messages": len(snapshot.get("messages", [])),
                    },
                    indent=2,
                )
            )
            continue

        try:
            result = run_turn(
                agent,
                {"messages": [{"role": "user", "content": text}]},
                config,
                context,
            )
        except Exception as exc:  # noqa: BLE001 - a CLI should not die on one bad turn
            print(f"\n  error: {exc}\n", file=sys.stderr)
            continue

        _print_reply(result)
        _drain_human_replies(agent, config, seen)


if __name__ == "__main__":
    main()
