"""Planner turn protocol.

The planner ends a turn with zero or more *directive* lines that the runtime executes:

    PLAN: <one-line decomposition summary>     (optional)
    DISPATCH:<role>:<one-line task>            (one PER sub-task; several = parallel fan-out)
    ASK: <a single question for the principal> (suspend and clarify)

Everything that is not a directive line is the planner's prose (a brief thought before a
dispatch, or the final answer when there are no directives). This module is pure (stdlib
only) so it can be unit-tested without a live model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DISPATCH_RE = re.compile(
    r"^\s*DISPATCH\s*:\s*(?P<role>[a-z_][a-z0-9_-]*)\s*:\s*(?P<task>.+?)\s*$",
    re.IGNORECASE,
)
ASK_RE = re.compile(r"^\s*ASK\s*:\s*(?P<q>.+?)\s*$", re.IGNORECASE)
PLAN_RE = re.compile(r"^\s*PLAN\s*:\s*(?P<s>.+?)\s*$", re.IGNORECASE)


@dataclass
class PlannerTurn:
    """One parsed planner reply."""

    plan_summary: str | None = None
    dispatches: list[tuple[str, str]] = field(default_factory=list)  # (role, task)
    ask: str | None = None
    prose: str = ""  # the reply minus directive lines


def parse_planner_turn(reply: str) -> PlannerTurn:
    plan_summary: str | None = None
    dispatches: list[tuple[str, str]] = []
    ask: str | None = None
    prose_lines: list[str] = []

    for line in reply.splitlines():
        m_dispatch = DISPATCH_RE.match(line)
        m_ask = ASK_RE.match(line)
        m_plan = PLAN_RE.match(line)
        if m_dispatch:
            dispatches.append((m_dispatch.group("role").lower(), m_dispatch.group("task").strip()))
        elif m_ask and ask is None:
            ask = m_ask.group("q").strip()
        elif m_plan and plan_summary is None:
            plan_summary = m_plan.group("s").strip()
        else:
            prose_lines.append(line)

    # Asking the principal takes precedence: hold any dispatches until they answer.
    if ask is not None:
        dispatches = []

    return PlannerTurn(
        plan_summary=plan_summary,
        dispatches=dispatches,
        ask=ask,
        prose="\n".join(prose_lines).strip(),
    )


def is_final(turn: PlannerTurn) -> bool:
    """True when the turn carries no directives — i.e. it's the answer to the principal."""
    return turn.ask is None and not turn.dispatches
