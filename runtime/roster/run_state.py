"""Resumable run state for the orchestration loop.

Holds the run's phase plus the round budgets (parallel fan-outs, critique rounds) and the
phase to resume after a mid-task clarification. Pure / no I/O so it is unit-testable. The
critique and suspend/resume fields are used by US2/US4; US1 uses the fan-out budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    DISPATCHING = "dispatching"
    CRITIQUING = "critiquing"
    SYNTHESIZING = "synthesizing"
    AWAITING_INPUT = "awaiting_input"


@dataclass
class OrchestrationState:
    status: RunStatus = RunStatus.IDLE
    fanouts_used: int = 0
    critique_used: int = 0
    max_fanouts: int = 2
    max_critique: int = 2
    resume_phase: RunStatus | None = None
    gathered: bool = False  # True once the initial fan-out's results have returned

    # -- fan-out budget (US1) --------------------------------------------------
    def can_fanout(self) -> bool:
        return self.fanouts_used < self.max_fanouts

    def note_fanout(self) -> None:
        self.fanouts_used += 1

    # -- critique budget (US2) -------------------------------------------------
    def can_critique(self) -> bool:
        return self.critique_used < self.max_critique

    def note_critique(self) -> None:
        self.critique_used += 1

    # -- suspend / resume (US4) ------------------------------------------------
    def suspend(self, resume_phase: RunStatus) -> None:
        self.resume_phase = resume_phase
        self.status = RunStatus.AWAITING_INPUT

    def resume(self) -> RunStatus:
        phase = self.resume_phase or RunStatus.DISPATCHING
        self.resume_phase = None
        self.status = phase
        return phase

    @property
    def awaiting_input(self) -> bool:
        return self.status == RunStatus.AWAITING_INPUT

    def reset(self) -> None:
        self.status = RunStatus.IDLE
        self.fanouts_used = 0
        self.critique_used = 0
        self.resume_phase = None
        self.gathered = False


@dataclass
class TurnResult:
    """Outcome of one principal turn: a final answer, or a pending clarification."""

    status: str  # "done" | "awaiting_input"
    text: str
