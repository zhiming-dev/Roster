"""Tests for the TaskResult + diff-artifact capture (spec 004, T014). Validates against schema."""

import json
from pathlib import Path

import jsonschema

from roster.protocol import ToolCall
from roster.task_result import (
    build_task_result,
    new_task_id,
    write_diff_artifact,
    write_task_result,
)
from roster.tools import ToolExecutor
from roster.workspace import WorkspaceManager

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (REPO_ROOT / "shared" / "schemas" / "task-result.schema.json").read_text(encoding="utf-8")
)


def _executor(git_repo, tmp_path):
    wt = WorkspaceManager(git_repo, tmp_path / "wts", "run_x").create("task")
    return ToolExecutor(wt)


def test_full_diff_captures_the_cumulative_changeset(git_repo, tmp_path):
    ex = _executor(git_repo, tmp_path)
    ex.execute(ToolCall("edit", path="src/new.py", body="A = 1\n"))
    ex.execute(ToolCall("edit", path="src/app.py", body="VALUE = 2\n"))
    patch = ex.full_diff()
    assert "src/new.py" in patch and "src/app.py" in patch
    assert "A = 1" in patch and "VALUE = 2" in patch


def test_build_task_result_validates_against_the_schema(git_repo, tmp_path):
    ex = _executor(git_repo, tmp_path)
    ex.execute(ToolCall("edit", path="src/new.py", body="A = 1\n"))
    patch = ex.full_diff()
    task_id = new_task_id()
    result = build_task_result(
        task_id=task_id, run_id="run_x", completed_by="coder", summary="Added src/new.py", patch=patch
    )
    jsonschema.validate(result, SCHEMA)  # raises on non-conformance
    assert result["artifacts"][0]["kind"] == "diff"
    assert result["artifacts"][0]["path"] == f"artifacts/{task_id}/diff.patch"
    assert result["metrics"]["filesChanged"] == 1


def test_empty_changeset_is_still_schema_valid(tmp_path):
    result = build_task_result(
        task_id=new_task_id(), run_id="run_x", completed_by="coder", summary="No changes", patch=""
    )
    jsonschema.validate(result, SCHEMA)
    assert "artifacts" not in result  # no diff → no artifact


def test_artifacts_and_result_are_written_to_disk(git_repo, tmp_path):
    ex = _executor(git_repo, tmp_path)
    ex.execute(ToolCall("edit", path="src/new.py", body="A = 1\n"))
    patch = ex.full_diff()
    task_id = new_task_id()
    runs = tmp_path / "runs"
    rel_diff = write_diff_artifact(runs, "run_x", task_id, patch)
    result = build_task_result(
        task_id=task_id, run_id="run_x", completed_by="coder", summary="x", patch=patch
    )
    rel_res = write_task_result(runs, "run_x", result)

    assert (runs / "run_x" / rel_diff).read_text(encoding="utf-8") == patch
    written = json.loads((runs / "run_x" / rel_res).read_text(encoding="utf-8"))
    assert written["taskId"] == task_id and written["status"] == "success"
    jsonschema.validate(written, SCHEMA)
