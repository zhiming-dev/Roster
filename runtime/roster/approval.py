"""The boundary approval gate's data layer (spec 004, US2/T018).

When a specialist's tool call is *gated* (a boundary-crossing / T3+ action), the runtime:

1. builds an **ActionProposal** that validates ``shared/schemas/action-proposal.schema.json``
   and writes it to ``runs/<runId>/proposals/<propId>.json`` (constitution VI);
2. surfaces a short, opinionated summary to the principal and suspends the run
   (``awaiting_input`` — reusing spec 001's suspend/resume, no new state machine);
3. records the principal's decision back onto the proposal file (append-only provenance gets
   the ``approval.requested`` / ``approval.resolved`` events at the orchestrator call site).

Pure plumbing — no model, bus, or subprocess here, so it is unit-testable in isolation.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .protocol import ToolCall

# `proposedBy` values the schema accepts; anything custom is clamped to the generic
# execution role rather than emitting an invalid document.
_PROPOSER_ENUM = frozenset({"qa", "coder", "reviewer", "researcher", "ops", "data", "planner"})

_ACTION_KINDS = {"exec": "shell.exec", "edit": "fs.write", "read": "fs.read"}


def new_prop_id() -> str:
    return f"prop_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class PendingApproval:
    """One gated action waiting on the principal, tied to the specialist it paused."""

    prop_id: str
    agent: str  # the paused agent's name (whose turn resumes after the decision)
    role: str  # its role, for the proposal's `proposedBy`
    call: ToolCall  # the gated tool call, replayed with approved=True on approve
    tier: str
    reason: str

    @property
    def action_text(self) -> str:
        return self.call.command or self.call.path or self.call.kind


def build_action_proposal(pending: PendingApproval, run_id: str) -> dict[str, Any]:
    """A schema-valid ActionProposal for one gated action (decision starts ``pending``)."""
    call = pending.call
    action: dict[str, Any] = {
        "kind": _ACTION_KINDS.get(call.kind, "shell.exec"),
        "summary": f"{pending.agent} wants to run a {pending.tier} action: {pending.action_text}",
    }
    if call.command:
        action["command"] = call.command
    if call.path:
        action["target"] = call.path
    return {
        "id": pending.prop_id,
        "runId": run_id,
        "taskId": f"task_{uuid.uuid4().hex[:12]}",
        "proposedBy": pending.role if pending.role in _PROPOSER_ENUM else "ops",
        "action": action,
        "riskTier": pending.tier,
        "rationale": (
            f"Requested by `{pending.agent}` while executing its dispatched task; stopped at "
            f"the sandbox boundary ({pending.reason})."
        ),
        "reversibilityPlan": (
            "No automatic rollback — the runtime cannot undo this once run; "
            "treat as irreversible when deciding."
        ),
        "recoverabilityState": {"backupVerified": False},
        "blastRadius": {"scope": "external", "affectedDescription": pending.reason},
        "proposedAt": _now_iso(),
        "decision": "pending",
    }


def _proposal_path(runs_dir: str | Path, run_id: str, prop_id: str) -> Path:
    return Path(runs_dir) / run_id / "proposals" / f"{prop_id}.json"


def write_action_proposal(runs_dir: str | Path, run_id: str, proposal: dict[str, Any]) -> str:
    """Write ``proposals/<propId>.json``; return the run-relative path."""
    path = _proposal_path(runs_dir, run_id, str(proposal["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"proposals/{proposal['id']}.json"


def record_decision(
    runs_dir: str | Path, run_id: str, prop_id: str, decision: str, decided_by: str = "principal"
) -> None:
    """Stamp the principal's decision onto the persisted proposal (best-effort)."""
    path = _proposal_path(runs_dir, run_id, prop_id)
    if not path.is_file():
        return
    proposal = json.loads(path.read_text(encoding="utf-8"))
    proposal["decision"] = decision
    proposal["decidedBy"] = decided_by
    proposal["decidedAt"] = _now_iso()
    path.write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def approval_summary(pending: PendingApproval) -> str:
    """The short, human-reviewable gate summary (per shared/approval-gate/SKILL.md — never a
    JSON dump). Sent to the principal as the run suspends."""
    return (
        f"[{pending.tier} — needs your approval] `{pending.agent}` wants to run:\n\n"
        f"    {pending.action_text}\n\n"
        f"Why it stopped: {pending.reason}.\n"
        'Reply **approve** to run it, or **reject** to skip it and continue without it.'
    )


# --- decision parsing ---------------------------------------------------------

_APPROVE_WORDS = frozenset(
    {"approve", "approved", "yes", "y", "ok", "okay", "allow", "allowed", "run", "go", "proceed"}
)
_REJECT_WORDS = frozenset(
    {"reject", "rejected", "no", "n", "deny", "denied", "skip", "dont", "don't", "cancel", "stop"}
)
# CJK phrases are matched by prefix (no word boundaries); longest-first so 不行/不要 win over 不.
_APPROVE_CJK = ("批准", "同意", "允许", "可以", "通过", "执行", "准")
_REJECT_CJK = ("拒绝", "驳回", "不要", "不行", "不用", "不准", "否", "别", "不")

_FIRST_WORD_RE = re.compile(r"[\s:,.;!?，。：；！？]+")


def parse_decision(text: str) -> str | None:
    """Map the principal's reply to ``"approve"`` / ``"reject"``, or ``None`` if ambiguous.

    Deliberately conservative (constitution I): only an explicit yes/no-shaped answer counts;
    anything ambiguous re-surfaces the question rather than guessing.
    """
    t = (text or "").strip().lower()
    if not t:
        return None
    for cjk in _REJECT_CJK:
        if t.startswith(cjk):
            return "reject"
    for cjk in _APPROVE_CJK:
        if t.startswith(cjk):
            return "approve"
    first = _FIRST_WORD_RE.split(t, 1)[0]
    if first in _APPROVE_WORDS:
        return "approve"
    if first in _REJECT_WORDS:
        return "reject"
    return None
