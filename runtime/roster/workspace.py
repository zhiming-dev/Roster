"""Per-run git worktree lifecycle — the Coder's sandbox (spec 004, T009).

Roster acts as a development agent over an operator-designated *target repository*. For each
run it carves out an isolated git **worktree** on a dedicated feature branch
(``feat/<runId>-<task-slug>``), so file/shell tools mutate that branch — never ``main`` and
never the target's primary working tree. Path confinement *inside* the worktree is enforced by
``boundary.resolve_in_worktree`` (the T003 resolver), exposed here as ``Worktree.resolve``.

This module shells out to ``git`` for worktree management. Methods are synchronous — git
worktree ops are quick setup/teardown; async callers wrap them in ``asyncio.to_thread`` (the
same pattern ``store.py`` uses for blocking work).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .boundary import resolve_in_worktree


class WorkspaceError(RuntimeError):
    """The target repo is missing/invalid/dirty, or a git worktree operation failed."""


@dataclass(frozen=True)
class Worktree:
    """A live per-run worktree: its directory, feature branch, and the base it forked from."""

    path: Path
    branch: str
    base_ref: str

    def resolve(self, rel_path: str) -> Path:
        """Resolve a worktree-relative path, rejecting escapes (T003 resolver)."""
        return Path(resolve_in_worktree(rel_path, str(self.path)))


def _slugify(text: str, *, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:max_len].strip("-") or "task"


class WorkspaceManager:
    """Creates and tears down the per-run worktree for one target repository."""

    def __init__(self, target_repo: str | Path, worktrees_root: str | Path, run_id: str) -> None:
        self.target = Path(target_repo)
        self.worktrees_root = Path(worktrees_root)
        self.run_id = run_id

    # -- git plumbing ----------------------------------------------------------

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["git", "-C", str(self.target), *args], capture_output=True, text=True
        )
        if check and proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip()
            raise WorkspaceError(f"git {' '.join(args)} failed: {detail}")
        return proc

    def _is_git_repo(self) -> bool:
        if not self.target.exists():
            return False
        proc = self._git("rev-parse", "--is-inside-work-tree", check=False)
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def _is_clean(self) -> bool:
        return self._git("status", "--porcelain").stdout.strip() == ""

    def _base_ref(self) -> str:
        ref = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if ref == "HEAD":  # detached — pin to the commit
            return self._git("rev-parse", "HEAD").stdout.strip()
        return ref

    def _branch_exists(self, branch: str) -> bool:
        proc = self._git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
        return proc.returncode == 0

    def _is_registered_worktree(self, path: Path) -> bool:
        listing = self._git("worktree", "list", "--porcelain", check=False).stdout
        want = path.resolve()
        for line in listing.splitlines():
            if line.startswith("worktree "):
                if Path(line[len("worktree ") :].strip()).resolve() == want:
                    return True
        return False

    # -- naming ----------------------------------------------------------------

    def branch_name(self, task_slug: str) -> str:
        return f"feat/{self.run_id}-{_slugify(task_slug)}"

    def worktree_path(self, task_slug: str) -> Path:
        return self.worktrees_root / f"{self.run_id}-{_slugify(task_slug)}"

    # -- lifecycle -------------------------------------------------------------

    def create(self, task_slug: str) -> Worktree:
        """Create — or reuse — the run's worktree on its feature branch.

        Reuses an already-registered worktree (preserving in-progress work); otherwise forks a
        fresh ``feat/…`` branch off the current base. Refuses a non-git target, and a dirty base
        when a new branch must be forked, rather than writing into an inconsistent tree.
        """
        if not self._is_git_repo():
            raise WorkspaceError(
                f"target repository is not a git repo (or does not exist): {self.target}"
            )
        base_ref = self._base_ref()
        branch = self.branch_name(task_slug)
        path = self.worktree_path(task_slug)

        self._git("worktree", "prune", check=False)

        if path.exists():
            if self._is_registered_worktree(path):
                return Worktree(path=path, branch=branch, base_ref=base_ref)
            shutil.rmtree(path)  # a stray, non-worktree dir is in the way — clear it

        # Forking a new branch off a dirty base risks losing uncommitted work — refuse.
        if not self._branch_exists(branch) and not self._is_clean():
            raise WorkspaceError(
                f"target repo working tree is dirty; commit or stash changes in {self.target} first"
            )

        self.worktrees_root.mkdir(parents=True, exist_ok=True)
        if self._branch_exists(branch):
            self._git("worktree", "add", str(path), branch)
        else:
            self._git("worktree", "add", "-b", branch, str(path), base_ref)
        return Worktree(path=path, branch=branch, base_ref=base_ref)

    def remove(self, task_slug: str, *, delete_branch: bool = False) -> None:
        """Remove the run's worktree (force). Optionally delete its feature branch too."""
        path = self.worktree_path(task_slug)
        self._git("worktree", "remove", "--force", str(path), check=False)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        self._git("worktree", "prune", check=False)
        if delete_branch:
            self._git("branch", "-D", self.branch_name(task_slug), check=False)
