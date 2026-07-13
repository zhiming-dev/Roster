"""Unit tests for the per-run worktree manager (spec 004, T009). Uses the ``git_repo`` fixture."""

import subprocess
from pathlib import Path

import pytest

from roster.boundary import PathEscape
from roster.workspace import WorkspaceError, WorkspaceManager


def _branch_of(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_create_makes_a_feature_branch_worktree(git_repo, tmp_path):
    wm = WorkspaceManager(git_repo, tmp_path / "wts", "run_x")
    wt = wm.create("Add validation helper")
    assert wt.path.exists()
    assert wt.branch == "feat/run_x-add-validation-helper"
    assert _branch_of(wt.path) == wt.branch
    # The base commit's files are checked out in the worktree.
    assert (wt.path / "README.md").exists()
    assert (wt.path / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_create_never_touches_main(git_repo, tmp_path):
    wm = WorkspaceManager(git_repo, tmp_path / "wts", "run_x")
    wt = wm.create("x")
    assert wt.base_ref == "main"
    assert wt.branch != "main"
    assert _branch_of(git_repo) == "main"  # the target's primary tree stays on main


def test_create_is_idempotent_and_preserves_in_progress_work(git_repo, tmp_path):
    wm = WorkspaceManager(git_repo, tmp_path / "wts", "run_x")
    wt1 = wm.create("task one")
    (wt1.path / "new.txt").write_text("wip", encoding="utf-8")
    wt2 = wm.create("task one")  # reuse
    assert wt2.path == wt1.path
    assert (wt2.path / "new.txt").read_text(encoding="utf-8") == "wip"


def test_refuses_a_non_git_target(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    wm = WorkspaceManager(plain, tmp_path / "wts", "run_x")
    with pytest.raises(WorkspaceError):
        wm.create("x")


def test_refuses_a_missing_target(tmp_path):
    wm = WorkspaceManager(tmp_path / "does-not-exist", tmp_path / "wts", "run_x")
    with pytest.raises(WorkspaceError):
        wm.create("x")


def test_refuses_a_dirty_base(git_repo, tmp_path):
    (git_repo / "README.md").write_text("uncommitted change\n", encoding="utf-8")
    wm = WorkspaceManager(git_repo, tmp_path / "wts", "run_x")
    with pytest.raises(WorkspaceError):
        wm.create("x")


def test_worktree_resolve_confines_paths(git_repo, tmp_path):
    wm = WorkspaceManager(git_repo, tmp_path / "wts", "run_x")
    wt = wm.create("x")
    inside = wt.resolve("src/app.py")
    assert str(inside).startswith(str(wt.path.resolve()))
    with pytest.raises(PathEscape):
        wt.resolve("../escape.txt")


def test_remove_deletes_the_worktree(git_repo, tmp_path):
    wm = WorkspaceManager(git_repo, tmp_path / "wts", "run_x")
    wt = wm.create("x")
    assert wt.path.exists()
    wm.remove("x")
    assert not wt.path.exists()


def test_branch_name_is_slugified_and_run_scoped(git_repo, tmp_path):
    wm = WorkspaceManager(git_repo, tmp_path / "wts", "run_x")
    assert wm.branch_name("Add: validation/helper!") == "feat/run_x-add-validation-helper"
    assert wm.branch_name("") == "feat/run_x-task"
