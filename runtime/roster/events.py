"""Orchestration event kinds emitted on the bus and consumed by the dashboard
(spec 002, US4). Each is a plain ``{kind, ts, ...payload}`` like every other bus
event; this module is the single source of truth for their names and shapes.
"""

from __future__ import annotations

from typing import Any

from .bus import bus

PLAN_PROPOSED = "plan.proposed"
TASK_DISPATCHED = "task.dispatched"
CRITIQUE_ROUND = "critique.round"
CLARIFICATION_REQUESTED = "clarification.requested"
CLARIFICATION_ANSWERED = "clarification.answered"


async def emit_plan_proposed(run_id: str, summary: str, tasks: list[dict[str, Any]]) -> None:
    await bus.publish(PLAN_PROPOSED, runId=run_id, summary=summary, tasks=tasks)


async def emit_task_dispatched(to: str, task: str, round: int) -> None:
    await bus.publish(TASK_DISPATCHED, **{"from": "planner", "to": to, "task": task, "round": round})


async def emit_critique_round(round: int, concern: str, action: str, to: str | None = None) -> None:
    await bus.publish(CRITIQUE_ROUND, round=round, concern=concern, action=action, to=to)


async def emit_clarification_requested(question: str) -> None:
    await bus.publish(CLARIFICATION_REQUESTED, question=question)


async def emit_clarification_answered(answer: str) -> None:
    await bus.publish(CLARIFICATION_ANSWERED, answer=answer)
