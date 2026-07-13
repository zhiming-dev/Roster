"""End-to-end US2 tests — the boundary approval gate (spec 004, T020).

A full ``Run`` drives a scripted Planner → Coder exchange in which the Coder attempts a
boundary-crossing command (``git push`` to a REAL local bare remote). Verified from the world,
not from prose: the remote only ever receives the branch when — and only when — the principal
approves (SC-002). Also covers reject, ambiguous answers, the persisted ActionProposal
(schema-valid, constitution VI), and the T017 process-group kill / output cap (SC-006).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import jsonschema
import pytest

from roster.approval import parse_decision
from roster.orchestrator import Run
from roster.provenance import runs_dir
from roster.tools import ToolExecutor
from roster.workspace import WorkspaceManager

PROPOSAL_SCHEMA = json.loads(
    (
        Path(__file__).resolve().parents[2] / "shared" / "schemas" / "action-proposal.schema.json"
    ).read_text(encoding="utf-8")
)


class _Scripted:
    """A provider stand-in that returns canned replies in order (default final when exhausted)."""

    def __init__(self, replies):
        self._replies = list(replies)

    async def chat(self, history):
        return self._replies.pop(0) if self._replies else "done."

    async def health(self):
        return {"ok": True}

    async def aclose(self):
        pass


def _add_bare_remote(git_repo: Path) -> Path:
    """A real local bare remote — push has an observable, offline side effect."""
    bare = git_repo.parent / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(git_repo), "remote", "add", "origin", str(bare)],
        check=True,
        capture_output=True,
    )
    return bare


def _remote_branches(bare: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(bare), "for-each-ref", "--format=%(refname:short)"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _gated_run(git_repo, runtime_config, monkeypatch, *, coder_replies=None):
    monkeypatch.setenv("ROSTER_RUNS_DIR", str(git_repo.parent / "runs"))
    run = Run(runtime_config(target_repo=git_repo))
    run.planner.provider = _Scripted(
        ["DISPATCH:coder:publish the branch", "Final: publication handled as decided."]
    )
    run.subagents["coder"].provider = _Scripted(
        coder_replies
        or [
            "Publishing.\nEXEC: git push origin HEAD",
            "Done — reported the push outcome.",
        ]
    )
    return run


async def test_boundary_command_suspends_and_writes_a_proposal(
    git_repo, runtime_config, monkeypatch
):
    bare = _add_bare_remote(git_repo)
    run = _gated_run(git_repo, runtime_config, monkeypatch)
    try:
        result = await run.handle_principal_message("publish the branch")

        # The run is paused for the principal; the command did NOT run (remote untouched).
        assert result.status == "awaiting_input"
        assert "approve" in result.text.lower()
        assert run.orch_state.awaiting_input and run.pending_approvals
        assert _remote_branches(bare) == ""

        # A schema-valid ActionProposal was persisted with decision=pending.
        props = list((runs_dir() / run.run_id / "proposals").glob("prop_*.json"))
        assert len(props) == 1
        proposal = json.loads(props[0].read_text(encoding="utf-8"))
        jsonschema.validate(proposal, PROPOSAL_SCHEMA)
        assert proposal["decision"] == "pending"
        assert proposal["action"]["command"] == "git push origin HEAD"
        assert proposal["riskTier"] == "T3"

        # Provenance recorded the request (constitution V).
        prov = (runs_dir() / run.run_id / "provenance.jsonl").read_text(encoding="utf-8")
        assert "approval.requested" in prov
    finally:
        await run.aclose()


async def test_approve_executes_the_action_and_resumes(git_repo, runtime_config, monkeypatch):
    bare = _add_bare_remote(git_repo)
    run = _gated_run(git_repo, runtime_config, monkeypatch)
    try:
        first = await run.handle_principal_message("publish the branch")
        assert first.status == "awaiting_input"
        assert _remote_branches(bare) == ""  # nothing ran yet

        second = await run.handle_principal_message("approve")

        # The push REALLY happened — the bare remote now has the run's feature branch.
        assert run._worktree.branch in _remote_branches(bare)
        # The coder saw the command's real outcome and the planner then answered.
        coder_history = " ".join(m["content"] for m in run.subagents["coder"].history)
        assert "[exec] $ git push origin HEAD" in coder_history and "exit 0" in coder_history
        assert second.status == "done"
        assert "Final" in second.text
        assert not run.pending_approvals and not run.orch_state.awaiting_input

        # The persisted proposal carries the decision; provenance has the resolution.
        props = list((runs_dir() / run.run_id / "proposals").glob("prop_*.json"))
        proposal = json.loads(props[0].read_text(encoding="utf-8"))
        assert proposal["decision"] == "approve" and proposal["decidedBy"] == "principal"
        prov = (runs_dir() / run.run_id / "provenance.jsonl").read_text(encoding="utf-8")
        assert "approval.resolved" in prov
    finally:
        await run.aclose()


async def test_reject_abandons_the_action_without_running_it(
    git_repo, runtime_config, monkeypatch
):
    bare = _add_bare_remote(git_repo)
    run = _gated_run(
        git_repo,
        runtime_config,
        monkeypatch,
        coder_replies=[
            "Publishing.\nEXEC: git push origin HEAD",
            "Understood — continuing without the push.",
        ],
    )
    try:
        first = await run.handle_principal_message("publish the branch")
        assert first.status == "awaiting_input"

        second = await run.handle_principal_message("reject")

        # Never executed: the remote stays empty, and the coder was told to move on.
        assert _remote_branches(bare) == ""
        coder_history = " ".join(m["content"] for m in run.subagents["coder"].history)
        assert "[approval denied]" in coder_history
        assert second.status == "done"
        # Abandoned exactly once — no re-proposal loop.
        assert not run.pending_approvals

        props = list((runs_dir() / run.run_id / "proposals").glob("prop_*.json"))
        proposal = json.loads(props[0].read_text(encoding="utf-8"))
        assert proposal["decision"] == "reject"
    finally:
        await run.aclose()


async def test_ambiguous_answer_re_surfaces_the_proposal(git_repo, runtime_config, monkeypatch):
    bare = _add_bare_remote(git_repo)
    run = _gated_run(git_repo, runtime_config, monkeypatch)
    try:
        first = await run.handle_principal_message("publish the branch")
        assert first.status == "awaiting_input"

        vague = await run.handle_principal_message("hmm, what would that do exactly?")

        # No guessed consent (constitution I): still suspended, still not executed.
        assert vague.status == "awaiting_input"
        assert "approve" in vague.text.lower()
        assert run.pending_approvals and _remote_branches(bare) == ""

        # An explicit decision still works afterwards.
        final = await run.handle_principal_message("reject")
        assert final.status == "done" and _remote_branches(bare) == ""
    finally:
        await run.aclose()


async def test_resolve_approval_by_id_is_equivalent_to_chat(
    git_repo, runtime_config, monkeypatch
):
    # The /api/approvals/{propId} sugar drives the same path as a chat "approve".
    bare = _add_bare_remote(git_repo)
    run = _gated_run(git_repo, runtime_config, monkeypatch)
    try:
        first = await run.handle_principal_message("publish the branch")
        assert first.status == "awaiting_input"
        prop_id = run.pending_approvals[0].prop_id
        assert run.has_pending_approval(prop_id)
        assert not run.has_pending_approval("prop_nonexistent")

        result = await run.resolve_approval(prop_id, "approve")

        assert result.status == "done"
        assert run._worktree.branch in _remote_branches(bare)
    finally:
        await run.aclose()


async def test_t4_action_is_refused_without_suspending(git_repo, runtime_config, monkeypatch):
    run = _gated_run(
        git_repo,
        runtime_config,
        monkeypatch,
        coder_replies=[
            "Wiping.\nEXEC: dd if=/dev/zero of=/dev/sda",
            "Cannot do that — refused as irreversible.",
        ],
    )
    try:
        result = await run.handle_principal_message("publish the branch")

        # No approval flow for T4: the run completes and no proposal was written.
        assert result.status == "done"
        assert not run.pending_approvals
        assert not (runs_dir() / run.run_id / "proposals").exists()
        coder_history = " ".join(m["content"] for m in run.subagents["coder"].history)
        assert "[denied]" in coder_history and "T4" in coder_history
    finally:
        await run.aclose()


# --- T017: bounded, tree-killing exec (SC-006) --------------------------------------


def _executor(git_repo, tmp_path, **kw) -> ToolExecutor:
    wt = WorkspaceManager(git_repo, tmp_path / "wts", "run_t17").create("task")
    return ToolExecutor(wt, **kw)


@pytest.mark.skipif(os.name != "posix", reason="process-group semantics are POSIX")
def test_timeout_kills_the_whole_process_tree(git_repo, tmp_path):
    # A wrapper that spawns a pipe-holding grandchild: without the group kill, communicate()
    # blocks until the grandchild exits (~30s). With it, we return right after the timeout.
    from roster.protocol import ToolCall

    ex = _executor(git_repo, tmp_path, timeout_s=1)
    start = time.monotonic()
    r = ex.execute(ToolCall("exec", command="sh -c 'sleep 30 & wait'"))
    elapsed = time.monotonic() - start
    assert r.timed_out and r.status == "error"
    assert elapsed < 10, f"kill did not take down the tree (took {elapsed:.1f}s)"


def test_output_is_capped_with_a_truncation_marker(git_repo, tmp_path):
    from roster.protocol import ToolCall

    ex = _executor(git_repo, tmp_path, max_output=1000)
    r = ex.execute(ToolCall("exec", command=f'{sys.executable} -c "print(\'x\' * 100000)"'))
    assert r.status == "ok" and r.truncated
    assert len(r.stdout) < 1200  # 1000 chars + the truncation marker
    assert "[truncated]" in r.stdout


# --- decision parsing ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("approve", "approve"),
        ("Approve.", "approve"),
        ("yes", "approve"),
        ("ok, run it", "approve"),
        ("批准", "approve"),
        ("同意执行", "approve"),
        ("reject", "reject"),
        ("No!", "reject"),
        ("deny it", "reject"),
        ("拒绝", "reject"),
        ("不要", "reject"),
        ("不可以", "reject"),
        ("", None),
        ("tell me more first", None),
        ("what does this do?", None),
    ],
)
def test_parse_decision(text, expected):
    assert parse_decision(text) == expected
