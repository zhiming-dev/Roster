"""Unit tests for the tool executor (spec 004, T010). Real git worktree + subprocess."""

import shlex
import sys
from pathlib import Path

from roster.protocol import ToolCall
from roster.tools import ToolExecutor
from roster.workspace import WorkspaceManager


def _executor(git_repo, tmp_path, **kw):
    wm = WorkspaceManager(git_repo, tmp_path / "wts", "run_x")
    wt = wm.create("task")
    return ToolExecutor(wt, **kw), wt


# -- read ----------------------------------------------------------------------


def test_read_returns_real_contents(git_repo, tmp_path):
    ex, _ = _executor(git_repo, tmp_path)
    r = ex.execute(ToolCall("read", path="src/app.py"))
    assert r.ok and r.content == "VALUE = 1\n"


def test_read_missing_file_is_error(git_repo, tmp_path):
    ex, _ = _executor(git_repo, tmp_path)
    assert ex.execute(ToolCall("read", path="nope.py")).status == "error"


def test_read_outside_worktree_is_denied(git_repo, tmp_path):
    ex, _ = _executor(git_repo, tmp_path)
    assert ex.execute(ToolCall("read", path="../secret")).status == "denied"


# -- edit ----------------------------------------------------------------------


def test_edit_creates_a_file_and_reports_a_diff(git_repo, tmp_path):
    ex, wt = _executor(git_repo, tmp_path)
    r = ex.execute(ToolCall("edit", path="src/util.py", body="def ok():\n    return True\n"))
    assert r.ok
    assert (wt.path / "src" / "util.py").read_text(encoding="utf-8") == "def ok():\n    return True\n"
    assert r.files and r.files[0].status == "added" and r.files[0].path == "src/util.py"
    assert "def ok" in r.patch


def test_edit_modifies_and_counts_changes(git_repo, tmp_path):
    ex, _ = _executor(git_repo, tmp_path)
    r = ex.execute(ToolCall("edit", path="src/app.py", body="VALUE = 2\n"))
    assert r.ok and r.files[0].status == "modified"
    assert r.files[0].additions == 1 and r.files[0].deletions == 1


def test_edit_outside_worktree_is_denied(git_repo, tmp_path):
    ex, wt = _executor(git_repo, tmp_path)
    r = ex.execute(ToolCall("edit", path="../evil.txt", body="x"))
    assert r.status == "denied"
    assert not (wt.path.parent / "evil.txt").exists()


# -- exec ----------------------------------------------------------------------


def test_exec_runs_a_benign_command(git_repo, tmp_path):
    ex, wt = _executor(git_repo, tmp_path)
    r = ex.execute(ToolCall("exec", command="git rev-parse --abbrev-ref HEAD"))
    assert r.ok and r.exit_code == 0
    assert wt.branch in r.stdout


def test_exec_reports_nonzero_exit(git_repo, tmp_path):
    ex, _ = _executor(git_repo, tmp_path)
    r = ex.execute(ToolCall("exec", command="git rev-parse --verify --quiet refs/heads/nope"))
    assert r.status == "error" and r.exit_code != 0


def test_exec_gates_a_boundary_command_without_running(git_repo, tmp_path):
    ex, _ = _executor(git_repo, tmp_path)
    r = ex.execute(ToolCall("exec", command="curl http://example.com"))
    assert r.status == "gated" and r.exit_code is None and r.tier == "T3"


def test_exec_unknown_command_is_error(git_repo, tmp_path):
    ex, _ = _executor(git_repo, tmp_path)
    assert ex.execute(ToolCall("exec", command="definitely-not-a-real-cmd-xyz")).status == "error"


def test_exec_times_out(git_repo, tmp_path):
    ex, wt = _executor(git_repo, tmp_path, timeout_s=1)
    (wt.path / "sleeper.py").write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    r = ex.execute(ToolCall("exec", command=f"{shlex.quote(sys.executable)} sleeper.py"))
    assert r.timed_out and r.status == "error"


# -- dispatch / feedback -------------------------------------------------------


def test_malformed_call_is_error(git_repo, tmp_path):
    ex, _ = _executor(git_repo, tmp_path)
    assert ex.execute(ToolCall("read", error="READ: requires a file path")).status == "error"


def test_as_feedback_prefixes_by_kind(git_repo, tmp_path):
    ex, _ = _executor(git_repo, tmp_path)
    assert ex.execute(ToolCall("read", path="src/app.py")).as_feedback().startswith("[read]")
    assert ex.execute(ToolCall("exec", command="curl http://x")).as_feedback().startswith("[blocked]")
