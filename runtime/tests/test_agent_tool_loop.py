"""Tests for the agent tool loop — READ/EDIT/EXEC driven through a real executor (spec 004, T011).

A real ``Agent`` runs against a scripted fake provider and a real ``ToolExecutor`` on a git
worktree, so the parse → execute → feed-back loop is exercised without a live model.
"""

import types

from roster.agent import Agent
from roster.tools import ToolExecutor
from roster.workspace import WorkspaceManager


class _ScriptedProvider:
    """Returns canned replies in order; records the history it was called with each turn."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.provider = "fake"
        self.target = "fake-model"
        self.endpoint = "local"
        self.seen: list[list[str]] = []

    async def chat(self, history):
        self.seen.append([m["content"] for m in history])
        return self._replies.pop(0) if self._replies else "done."

    async def health(self):
        return {"ok": True}


def _agent(git_repo, tmp_path, replies):
    wt = WorkspaceManager(git_repo, tmp_path / "wts", "run_x").create("task")
    cfg = types.SimpleNamespace(
        name="coder",
        role="coder",
        provider=types.SimpleNamespace(provider="fake", target="fake-model", endpoint="local"),
    )
    provider = _ScriptedProvider(replies)
    agent = Agent(
        cfg=cfg, provider=provider, executor=ToolExecutor(wt),
        history=[{"role": "system", "content": "sys"}],
    )
    return agent, wt, provider


async def test_edit_directive_writes_the_file_then_answers(git_repo, tmp_path):
    agent, wt, _ = _agent(
        git_repo, tmp_path,
        ["I'll add it.\nEDIT: src/new.py\n```python\nX = 1\n```", "Done — added src/new.py."],
    )
    reply = await agent.chat("add src/new.py with X = 1")
    assert reply == "Done — added src/new.py."
    assert (wt.path / "src" / "new.py").read_text(encoding="utf-8") == "X = 1\n"


async def test_read_directive_feeds_contents_back(git_repo, tmp_path):
    agent, _, provider = _agent(
        git_repo, tmp_path, ["Let me check.\nREAD: src/app.py", "It sets VALUE = 1."]
    )
    reply = await agent.chat("what does app.py contain?")
    assert reply == "It sets VALUE = 1."
    # The read result was fed back into history before the 2nd model call.
    assert any("[read] src/app.py" in m and "VALUE = 1" in m for m in provider.seen[1])


async def test_exec_directive_runs_and_feeds_output(git_repo, tmp_path):
    agent, wt, provider = _agent(
        git_repo, tmp_path,
        ["Running.\nEXEC: git rev-parse --abbrev-ref HEAD", "On the feature branch."],
    )
    reply = await agent.chat("what branch?")
    assert reply == "On the feature branch."
    assert any("[exec]" in m and wt.branch in m for m in provider.seen[1])


async def test_gated_command_pauses_the_turn_for_approval(git_repo, tmp_path):
    # US2: a boundary command is NOT run and the turn SUSPENDS (ApprovalPending) with the
    # directive kept in history, so the principal's decision can resume it in place.
    import pytest

    from roster.tools import ApprovalPending

    agent, _, provider = _agent(
        git_repo, tmp_path,
        ["I'll push.\nEXEC: git push origin main", "Continuing after the decision."],
    )
    with pytest.raises(ApprovalPending) as exc_info:
        await agent.chat("push please")
    assert exc_info.value.call.command == "git push origin main"
    assert exc_info.value.result.gated and exc_info.value.result.exit_code is None
    assert agent.status == "blocked"
    # History still ends with the directive reply — resumable in place.
    assert agent.history[-1]["role"] == "assistant"
    assert "EXEC: git push origin main" in agent.history[-1]["content"]

    # Rejection feedback resumes the same turn to a final answer.
    reply = await agent.resume_turn("[approval denied] The principal rejected it.")
    assert reply == "Continuing after the decision."
    assert agent.status == "idle"


async def test_t4_command_is_refused_outright_without_pausing(git_repo, tmp_path):
    # An irreversible (T4) action never even reaches the approval gate: refused inline.
    agent, _, provider = _agent(
        git_repo, tmp_path,
        ["Wiping.\nEXEC: dd if=/dev/zero of=/dev/sda", "Understood — cannot do that."],
    )
    reply = await agent.chat("wipe the disk")
    assert reply == "Understood — cannot do that."
    assert any("[denied]" in m and "T4" in m for m in provider.seen[1])


async def test_no_directive_returns_immediately(git_repo, tmp_path):
    agent, _, provider = _agent(git_repo, tmp_path, ["Just a plain answer."])
    reply = await agent.chat("hi")
    assert reply == "Just a plain answer."
    assert len(provider.seen) == 1  # one model call, no tool round-trip


async def test_malformed_edit_feeds_a_corrective_message(git_repo, tmp_path):
    agent, wt, provider = _agent(
        git_repo, tmp_path,
        [
            "EDIT: src/x.py",  # no fenced body → malformed
            "Sorry, properly now.\nEDIT: src/x.py\n```\nY = 2\n```",
            "Fixed.",
        ],
    )
    reply = await agent.chat("add x")
    assert reply == "Fixed."
    assert (wt.path / "src" / "x.py").read_text(encoding="utf-8") == "Y = 2\n"
    assert any("fenced" in m.lower() for m in provider.seen[1])
