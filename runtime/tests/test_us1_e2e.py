"""End-to-end US1 test (spec 004, T015).

A full ``Run`` drives a scripted Planner → Coder exchange: the Coder reads a file, edits a new
one, and runs a command against a REAL worktree. Verified from disk — the worktree file, the
``diff.patch`` artifact, and the schema-valid ``TaskResult`` — not the Coder's prose (SC-001,
SC-004). Only the LLM is faked; the executor, worktree, and git are real.
"""

import json
from pathlib import Path

import jsonschema

from roster.orchestrator import Run
from roster.provenance import runs_dir

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "shared" / "schemas" / "task-result.schema.json").read_text(
        encoding="utf-8"
    )
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


async def test_coder_reads_edits_and_runs_end_to_end(git_repo, runtime_config, monkeypatch):
    monkeypatch.setenv("ROSTER_RUNS_DIR", str(git_repo.parent / "runs"))
    run = Run(runtime_config(target_repo=git_repo))
    try:
        # Planner: dispatch to the coder, then answer. Coder: read → edit → exec → report.
        run.planner.provider = _Scripted(
            ["DISPATCH:coder:implement the helper module", "Done — the coder added the helper."]
        )
        run.subagents["coder"].provider = _Scripted(
            [
                "First, inspect the seed.\nREAD: src/app.py",
                "Add the helper.\nEDIT: src/helper.py\n```\ndef help():\n    return 1\n```",
                "Confirm the branch.\nEXEC: git rev-parse --abbrev-ref HEAD",
                "Done: read app.py, added helper.py, verified the branch.",
            ]
        )

        result = await run.handle_principal_message("add a helper module")
        assert result.status == "done"

        # 1. The edit really exists on disk in the worktree — not just claimed in prose.
        helper = run._worktree.path / "src" / "helper.py"
        assert helper.read_text(encoding="utf-8") == "def help():\n    return 1\n"

        # 2. A diff artifact + a schema-valid TaskResult were written under runs/<runId>/.
        run_dir = runs_dir() / run.run_id
        diffs = list((run_dir / "artifacts").glob("*/diff.patch"))
        assert diffs, "no diff.patch artifact written"
        assert "src/helper.py" in diffs[0].read_text(encoding="utf-8")
        results = list((run_dir / "results").glob("*.json"))
        assert results, "no TaskResult written"
        task_result = json.loads(results[0].read_text(encoding="utf-8"))
        jsonschema.validate(task_result, SCHEMA)
        assert task_result["completedBy"] == "coder"
        assert task_result["metrics"]["filesChanged"] >= 1

        # 3. The READ returned real contents and EXEC's real exit code were fed back to the Coder.
        coder_history = " ".join(m["content"] for m in run.subagents["coder"].history)
        assert "[read] src/app.py" in coder_history and "VALUE = 1" in coder_history
        assert "[exec]" in coder_history and "exit 0" in coder_history
    finally:
        await run.aclose()
