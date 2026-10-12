"""Exercise both human gates with real git, file edits, tests and patch application."""

import asyncio
import json
import shlex
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import yaml

from roster.orchestrator import Run
from roster.protocol import ToolCall
from roster.tools import ToolExecutor
from roster.workflow import validate


class Scripted:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    async def chat(self, history):
        self.calls += 1
        return self.replies.pop(0) if self.replies else "Done"

    async def aclose(self):
        pass


def python_command(code):
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


@pytest.fixture
def change_run(git_repo, runtime_config, monkeypatch):
    monkeypatch.setenv("ROSTER_RUNS_DIR", str(git_repo.parent / "runs"))
    path = runtime_config(target_repo=git_repo)
    config = yaml.safe_load(path.read_text())
    config["agents"]["reviewer"] = {
        "role": "reviewer",
        "agent_file": str(Path(__file__).resolve().parents[2] / "reviewer-agent/reviewer.agent.md"),
        "tools": ["read"],
    }
    path.write_text(yaml.safe_dump(config))
    run = Run(path)
    run.planner.provider = Scripted(["Change VALUE in src/app.py to 2. Preserve all other behavior."])
    run.subagents["coder"].provider = Scripted(["EDIT: src/app.py\n```\nVALUE = 2\n```", "Implemented the requested change."])
    run.subagents["reviewer"].provider = Scripted(["src/app.py matches the approved scope.\nREVIEW: PASS"])
    return run, path, git_repo


async def propose(run, command=None):
    command = command or python_command("from pathlib import Path; assert Path('src/app.py').read_text() == 'VALUE = 2\\n'")
    result = await run.change.start("Change VALUE to 2", command)
    assert result.status == "awaiting_input", result.text
    assert run.change.phase == "plan"
    return run.change.data["gateId"]


async def approve_plan(run, command=None):
    gate = await propose(run, command)
    return await run.change.decide(gate, "approve")


async def test_complete_pipeline_requires_both_decisions_and_patch_applies(change_run, tmp_path):
    run, _, target = change_run
    try:
        gate = await propose(run)
        assert run.subagents["coder"].provider.calls == 0
        assert (run._worktree.path / "src/app.py").read_text() == "VALUE = 1\n"
        with pytest.raises(ValueError):
            run.change.delivery()
        result = await run.change.decide(gate, "approve")
        assert result.status == "awaiting_input", result.text
        assert run.change.phase == "diff", run.change.public()
        assert run.change.data["testResult"]["exit_code"] == 0
        assert run.subagents["reviewer"].provider.calls == 1
        assert (target / "src/app.py").read_text() == "VALUE = 1\n"
        with pytest.raises(ValueError):
            run.change.delivery()
        with pytest.raises(ValueError):
            await run.change.decide(gate, "approve")
        await run.change.decide(run.change.data["gateId"], "approve")
        patch = run.change.delivery()
        checkout = tmp_path / "apply"
        subprocess.run(["git", "clone", str(target), str(checkout)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(checkout), "apply", "--check", str(patch)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True, capture_output=True)
        assert (checkout / "src/app.py").read_text() == "VALUE = 2\n"
        validate(json.loads((run.change.root / "plan.ratified.json").read_text()), "plan.schema.json")
        validate(json.loads(run.change.path.read_text()), "workflow.schema.json")
    finally:
        await run.aclose()


@pytest.mark.parametrize("phase", ["plan", "diff"])
async def test_reject_does_not_deliver_or_execute_again(change_run, phase):
    run, _, _ = change_run
    try:
        await propose(run)
        if phase == "diff":
            await run.change.decide(run.change.data["gateId"], "approve")
        before = run.subagents["coder"].provider.calls
        await run.change.decide(run.change.data["gateId"], "reject")
        assert run.change.phase == "rejected"
        assert run.subagents["coder"].provider.calls == before
        with pytest.raises(ValueError):
            run.change.delivery()
    finally:
        await run.aclose()


@pytest.mark.parametrize("review", ["A blocking bug in src/app.py.\nREVIEW: FAIL", "Looks fine", ""])
async def test_review_must_explicitly_pass_before_tests(change_run, review):
    run, _, _ = change_run
    run.subagents["reviewer"].provider = Scripted([review])
    try:
        await approve_plan(run)
        assert run.change.phase == "blocked"
        assert "testResult" not in run.change.data
    finally:
        await run.aclose()


@pytest.mark.parametrize("command", [python_command("raise SystemExit(7)"), "nonexistent_test_runner"])
async def test_failing_or_missing_test_command_prevents_delivery(change_run, command):
    run, _, _ = change_run
    try:
        await approve_plan(run, command)
        assert run.change.phase == "blocked"
        assert run.change.data["testResult"]["exit_code"] != 0
    finally:
        await run.aclose()


async def test_reviewer_cannot_edit_or_execute_even_when_it_asks(change_run):
    run, _, _ = change_run
    run.subagents["reviewer"].provider = Scripted([
        "EDIT: src/app.py\n```\nVALUE = 99\n```",
        f"EXEC: {python_command('raise SystemExit(9)')}",
        "REVIEW: PASS",
    ])
    try:
        await approve_plan(run)
        assert run.change.phase == "diff", run.change.public()
        assert (run._worktree.path / "src/app.py").read_text() == "VALUE = 2\n"
        executor = run.subagents["reviewer"].executor
        assert executor.execute(ToolCall("edit", path="src/app.py", body="bad"), approved=True).status == "denied"
        assert executor.execute(ToolCall("exec", command="git status"), approved=True).status == "denied"
    finally:
        await run.aclose()


@pytest.mark.parametrize("phase", ["plan", "diff"])
async def test_restart_restores_human_gate_without_reexecuting(change_run, phase):
    run, config, _ = change_run
    await propose(run)
    if phase == "diff":
        await run.change.decide(run.change.data["gateId"], "approve")
    gate_id = run.change.data["gateId"]
    run_id = run.run_id
    await run.aclose()
    restored = Run(config, run_id=run_id)
    try:
        assert restored.change.phase == phase
        assert restored.change.data["gateId"] == gate_id
        if phase == "diff":
            await restored.change.decide(gate_id, "approve")
            assert restored.change.phase == "delivered"
        else:
            await restored.change.decide(gate_id, "reject")
            assert (restored._worktree.path / "src/app.py").read_text() == "VALUE = 1\n"
    finally:
        await restored.aclose()


async def test_changed_diff_invalidates_human_approval(change_run):
    run, _, _ = change_run
    try:
        await approve_plan(run)
        (run._worktree.path / "src/app.py").write_text("VALUE = 99\n")
        await run.change.decide(run.change.data["gateId"], "approve")
        assert run.change.phase == "blocked"
        assert not (run.change.root / "delivery.patch").exists()
    finally:
        await run.aclose()


async def test_test_command_must_not_change_reviewed_patch(change_run):
    run, _, _ = change_run
    try:
        await approve_plan(run, python_command("from pathlib import Path; Path('src/app.py').write_text('VALUE = 3\\n')"))
        assert run.change.phase == "blocked"
        assert "changed the patch" in run.change.data["message"]
    finally:
        await run.aclose()


async def test_action_gate_restores_and_continues_into_review(change_run):
    run, config, _ = change_run
    run.subagents["coder"].provider = Scripted(["EXEC: curl https://example.com"])
    await approve_plan(run)
    assert run.change.phase == "action"
    pending = run.pending_approvals[0].prop_id
    await run.aclose()
    restored = Run(config, run_id=run.run_id)
    restored.subagents["coder"].provider = Scripted(["EDIT: src/app.py\n```\nVALUE = 2\n```", "Done without network access"])
    restored.subagents["reviewer"].provider = Scripted(["REVIEW: PASS"])
    try:
        assert restored.has_pending_approval(pending)
        await restored.resolve_approval(pending, "reject")
        assert restored.change.phase == "diff", restored.change.public()
        assert not restored.pending_approvals
    finally:
        await restored.aclose()


async def test_interrupted_execution_is_not_automatically_repeated(change_run):
    run, config, _ = change_run
    await propose(run)
    await run.change.transition("coding", "working")
    await run.aclose()
    restored = Run(config, run_id=run.run_id)
    try:
        assert restored.change.phase == "blocked"
        assert "interrupted" in restored.change.data["message"]
    finally:
        await restored.aclose()


async def test_api_delivers_only_approved_patch_and_rejects_duplicate_decisions(change_run, monkeypatch):
    from roster import server
    run, _, _ = change_run
    monkeypatch.setattr(server, "_run", run)
    monkeypatch.setattr(server, "_operation_lock", asyncio.Lock())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
        try:
            await propose(run)
            assert (await client.get(f"/api/changes/{run.run_id}/patch")).status_code == 404
            gate = run.change.data["gateId"]
            response = await client.post(f"/api/change/{gate}", json={"decision": "approve"})
            assert response.status_code == 200
            assert response.json()["change"]["phase"] == "diff"
            assert (await client.post(f"/api/change/{gate}", json={"decision": "approve"})).status_code == 409
            await client.post(f"/api/change/{run.change.data['gateId']}", json={"decision": "approve"})
            response = await client.get(f"/api/changes/{run.run_id}/patch")
            assert response.status_code == 200
            assert response.content == run.change.delivery().read_bytes()
            async with server._operation_lock:
                assert (await client.post("/api/reset")).status_code == 409
        finally:
            await run.aclose()


def test_snapshot_includes_binary_files_without_mutating_index(change_run):
    run, _, _ = change_run
    executor = ToolExecutor(run._worktree)
    base = executor._git("rev-parse", "HEAD").stdout.strip()
    before = executor._git("diff", "--cached").stdout
    (run._worktree.path / "asset.bin").write_bytes(b"\x00\xff\x01\x02")
    patch = executor.snapshot_patch(base)
    assert "GIT binary patch" in patch
    assert executor._git("diff", "--cached").stdout == before
