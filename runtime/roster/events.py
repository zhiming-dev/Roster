"""Orchestration event kinds emitted on the bus and consumed by the dashboard
(spec 002, US4; spec 004 tool/approval events). Each is a plain ``{kind, ts, ...payload}``
like every other bus event; this module is the single source of truth for their names and
shapes, mirrored by the frontend in ``frontend/src/types/events.ts``.

These helpers publish the **live** bus event only. Append-only provenance is emitted
separately at each call site that holds a ``ProvenanceLog`` (as the orchestrator does:
``events.emit_*`` for the bus, ``self.prov.emit`` for the log) so the two concerns stay
decoupled.
"""

from __future__ import annotations

from typing import Any

from .bus import bus

PLAN_PROPOSED = "plan.proposed"
TASK_DISPATCHED = "task.dispatched"
CRITIQUE_ROUND = "critique.round"
CLARIFICATION_REQUESTED = "clarification.requested"
CLARIFICATION_ANSWERED = "clarification.answered"

# Tool-execution + approval events (spec 004).
TOOL_FILE = "tool.file"  # phase: "read" | "write" | "diff"
TOOL_EXEC = "tool.exec"  # phase: "command" | "output"
APPROVAL_REQUESTED = "approval.requested"
APPROVAL_RESOLVED = "approval.resolved"


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


def _compact(pairs: tuple[tuple[str, Any], ...]) -> dict[str, Any]:
    """Keep only the payload fields that were actually supplied (no null spam)."""
    return {k: v for k, v in pairs if v is not None}


async def emit_tool_file(
    agent: str,
    phase: str,
    *,
    path: str | None = None,
    size: int | None = None,
    files: list[dict[str, Any]] | None = None,
    patch: str | None = None,
    truncated: bool | None = None,
) -> None:
    """A Coder/E2E file action. ``phase`` ``read``/``write`` carry ``path`` (+ ``bytes``);
    ``diff`` carries a per-file ``files`` summary and the unified ``patch``."""
    extra = _compact(
        (("path", path), ("bytes", size), ("files", files), ("patch", patch), ("truncated", truncated))
    )
    await bus.publish(TOOL_FILE, agent=agent, phase=phase, **extra)


async def emit_tool_exec(
    agent: str,
    phase: str,
    command: str,
    *,
    exit_code: int | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    duration_ms: int | None = None,
    timed_out: bool | None = None,
    truncated: bool | None = None,
) -> None:
    """A shell command. ``phase`` ``command`` announces it; ``output`` carries the result
    (``exitCode``, captured ``stdout``/``stderr``, ``durationMs``, ``timedOut``, ``truncated``)."""
    extra = _compact(
        (
            ("exitCode", exit_code),
            ("stdout", stdout),
            ("stderr", stderr),
            ("durationMs", duration_ms),
            ("timedOut", timed_out),
            ("truncated", truncated),
        )
    )
    await bus.publish(TOOL_EXEC, agent=agent, phase=phase, command=command, **extra)


async def emit_approval_requested(
    agent: str, prop_id: str, tier: str, action: str, summary: str
) -> None:
    """A boundary-crossing / T3+ action blocked and surfaced for human approval."""
    await bus.publish(
        APPROVAL_REQUESTED, agent=agent, propId=prop_id, tier=tier, action=action, summary=summary
    )


async def emit_approval_resolved(prop_id: str, decision: str) -> None:
    """The principal's decision on a pending proposal — ``approved`` or ``rejected``."""
    await bus.publish(APPROVAL_RESOLVED, propId=prop_id, decision=decision)
