"""Shared pytest fixtures for the runtime tests (spec 004, T001).

``git_repo`` builds a throwaway, fully-initialized git repository in a tmp dir — a stand-in for
the operator's *target repository* — so worktree/executor tests can run real ``git`` without
touching any real repo. Requires ``git`` on PATH (a spec-004 assumption).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def init_git_repo(path: Path) -> Path:
    """Create a git repo at ``path`` with one seed commit on a ``main`` branch."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init")
    # Deterministic identity + no signing, so commits work in a bare CI environment.
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Roster Test")
    _git(path, "config", "commit.gpgsign", "false")
    _git(path, "config", "core.autocrlf", "false")  # preserve LF on checkout (Windows-stable)
    (path / "README.md").write_text("seed\n", encoding="utf-8", newline="\n")
    (path / "src").mkdir(exist_ok=True)
    (path / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "seed")
    _git(path, "branch", "-M", "main")  # normalize the branch name across git versions
    return path


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A fresh target-style git repo (clean working tree, one commit on ``main``)."""
    return init_git_repo(tmp_path / "target")


@pytest.fixture
def runtime_config(tmp_path: Path):
    """Factory → path to a minimal ``agents.config.yaml`` (planner + coder + researcher).

    References the real agent .md files and an Ollama provider (lazily constructed — no network
    on ``Run`` init). Pass ``target_repo`` to enable the Coder's file/shell tools.
    """

    def _af(rel: str) -> str:
        return (Path(__file__).resolve().parents[2] / rel).as_posix()

    def _make(*, target_repo=None) -> Path:
        lines = ["queue:", "  max_concurrency: 1", "search:", "  enabled: false"]
        if target_repo is not None:
            lines += [
                "workspace:",
                f'  target_repo: "{Path(target_repo).as_posix()}"',
                f'  worktrees_root: "{(tmp_path / "wts").as_posix()}"',
            ]
        lines += [
            "defaults:",
            "  provider: ollama",
            "  endpoint: http://localhost:11434",
            "  model: llama3.1:8b",
            "agents:",
            "  planner:",
            f'    agent_file: "{_af("planner-agent/planner.agent.md")}"',
            "    role: planner",
            "  coder:",
            f'    agent_file: "{_af("coder-agent/coder.agent.md")}"',
            "    role: coder",
            "    tools: [read, edit, execute]",
            "  researcher:",
            f'    agent_file: "{_af("researcher-agent/researcher.agent.md")}"',
            "    role: researcher",
            "    tools: [search]",
        ]
        path = tmp_path / "agents.config.yaml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    return _make
