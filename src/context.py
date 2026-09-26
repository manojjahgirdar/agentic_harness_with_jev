"""Runtime context for the support agent.

Passed per invocation as `config={"context": SupportContext(...)}` so tools and
middleware know which customer they are acting for without the model being able to
claim a different one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SupportContext:
    customer_id: str
    """Authenticated customer. Never taken from model output."""

    channel: str = "cli"
    """Where the conversation is happening. Reserved for the future UI."""
