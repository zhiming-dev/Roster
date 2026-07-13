"""Boundary classification and worktree path confinement — the safety core (spec 004).

Two pure functions the tool-execution layer calls *before* it touches anything:

- ``resolve_in_worktree(rel_path, root)`` — resolve a relative path against the run's git
  worktree and confirm it stays inside. Rejects absolute paths, ``..`` escapes, and
  symlink escapes (the only filesystem touch is ``os.path.realpath``). Raises ``PathEscape``.
- ``classify_action(tool, ...)`` — decide a proposed action's risk tier (T0–T4) and whether
  it may auto-run inside the sandbox or must stop at the human-approval gate. A conservative
  denylist for shell (network egress, ``git push``, ``sudo``, out-of-tree deletes, deploys,
  destructive host ops, command chaining/substitution); everything ambiguous is *up-tiered*.

Both are pure (stdlib only) so the safety line is unit-testable without a model, network, or
subprocess. Tier vocabulary follows ``shared/approval-gate/SKILL.md`` (T0 read-only …
T4 irreversible). The rule of thumb, per the constitution: **when in doubt, classify up.**
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass

# Risk tiers, per shared/approval-gate/SKILL.md. Ordered for severity comparison.
TIERS = ("T0", "T1", "T2", "T3", "T4")
_TIER_RANK = {t: i for i, t in enumerate(TIERS)}


class PathEscape(ValueError):
    """A path resolved outside the run's worktree (absolute, ``..``, or symlink escape)."""


@dataclass(frozen=True)
class ActionClass:
    """The classification of one proposed tool action.

    ``auto`` True → the action is inside the sandbox at T0–T2 and runs automatically (logged).
    ``auto`` False → the action crosses the boundary or is T3+; it MUST stop at the approval
    gate before execution. ``reason`` is a short human-readable justification for the gate
    summary and the provenance record.
    """

    tier: str
    auto: bool
    reason: str


# --- path confinement --------------------------------------------------------

_WIN_DRIVE = re.compile(r"^[A-Za-z]:")


def _looks_absolute(p: str) -> bool:
    # Reject POSIX-absolute, Windows drive-absolute, and UNC paths regardless of host OS,
    # so a model on Linux still can't smuggle a Windows path (and vice-versa).
    return os.path.isabs(p) or bool(_WIN_DRIVE.match(p)) or p.startswith("\\\\") or p.startswith("//")


def resolve_in_worktree(rel_path: str, root: str) -> str:
    """Resolve ``rel_path`` under ``root`` and confirm containment. Return the absolute path.

    Raises ``PathEscape`` for empty, absolute, ``..``-escaping, or symlink-escaping paths.
    """
    if not rel_path or not rel_path.strip():
        raise PathEscape("empty path")
    if "\x00" in rel_path:
        raise PathEscape("path contains a NUL byte")
    if _looks_absolute(rel_path):
        raise PathEscape(f"absolute path not allowed: {rel_path!r}")

    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, rel_path))
    if candidate != root_real and not candidate.startswith(root_real + os.sep):
        raise PathEscape(f"path escapes the worktree: {rel_path!r}")
    return candidate


# --- action classification ---------------------------------------------------

# Shell programs / phrases that cross the sandbox boundary. Conservative and case-folded.
_ESCALATE = frozenset({"sudo", "su", "doas", "runas"})
_NETWORK = frozenset(
    {"curl", "wget", "nc", "ncat", "netcat", "telnet", "ssh", "scp", "sftp", "rsync", "ftp"}
)
_DEPLOY = frozenset({"kubectl", "helm", "terraform", "twine", "az", "aws", "gcloud"})
_DESTRUCTIVE = frozenset(
    {"mkfs", "dd", "format", "fdisk", "diskpart", "shutdown", "reboot", "halt", "poweroff"}
)
_DELETE = frozenset({"rm", "del", "erase", "rmdir", "rd"})
# git subcommands that reach a remote (network / boundary).
_GIT_REMOTE = frozenset({"push", "pull", "fetch", "clone", "ls-remote"})
# Operators that chain or substitute commands — a benign prefix must not hide a boundary suffix.
_CHAIN_RE = re.compile(r"\|\||&&|;|\||\n")
_SUBST_RE = re.compile(r"\$\(|`|>\(|<\(")


def _first_subcommand(args: list[str]) -> str | None:
    """First non-flag token — e.g. the git subcommand in ``git -C . push``."""
    for a in args:
        if not a.startswith("-"):
            return a.lower()
    return None


def _targets_outside(args: list[str]) -> bool:
    """True if any argument points outside the worktree (absolute, drive, UNC, or ``..``)."""
    for a in args:
        if a.startswith("-"):
            continue
        if _looks_absolute(a):
            return True
        parts = re.split(r"[\\/]+", a)
        if ".." in parts or a in ("/", "~"):
            return True
    return False


def _classify_segment(segment: str) -> ActionClass:
    cmd = segment.strip()
    if not cmd:
        return ActionClass("T2", True, "shell within the worktree")
    if _SUBST_RE.search(cmd):
        return ActionClass("T3", False, "command substitution — gated for review")
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError:
        return ActionClass("T3", False, "unparseable command (unbalanced quotes) — gated")
    if not tokens:
        return ActionClass("T2", True, "shell within the worktree")

    prog = os.path.basename(tokens[0]).lower()
    prog_root = prog.split(".", 1)[0]  # mkfs.ext4 -> mkfs
    args = tokens[1:]

    if prog in _ESCALATE:
        return ActionClass("T3", False, f"privilege escalation ({prog})")
    if prog in _NETWORK:
        return ActionClass("T3", False, f"network egress ({prog})")
    if prog in _DESTRUCTIVE or prog_root in _DESTRUCTIVE:
        return ActionClass("T4", False, f"destructive host operation ({prog})")
    if prog == "git":
        sub = _first_subcommand(args)
        if sub in _GIT_REMOTE:
            return ActionClass("T3", False, f"git {sub} reaches a remote")
    if prog in _DEPLOY:
        return ActionClass("T3", False, f"deploy/publish beyond the sandbox ({prog})")
    if prog == "docker" and _first_subcommand(args) == "push":
        return ActionClass("T3", False, "docker push to a registry")
    if prog in ("npm", "pnpm", "yarn") and _first_subcommand(args) == "publish":
        return ActionClass("T3", False, f"{prog} publish to a registry")
    if prog in _DELETE and _targets_outside(args):
        return ActionClass("T3", False, "delete outside the worktree")

    return ActionClass("T2", True, "shell within the worktree")


def _more_severe(a: ActionClass, b: ActionClass) -> ActionClass:
    # A gated action always dominates; otherwise the higher tier wins.
    if a.auto != b.auto:
        return a if not a.auto else b
    return a if _TIER_RANK[a.tier] >= _TIER_RANK[b.tier] else b


def _classify_exec(command: str) -> ActionClass:
    cmd = (command or "").strip()
    if not cmd:
        return ActionClass("T3", False, "empty command")
    segments = [s for s in _CHAIN_RE.split(cmd) if s.strip()]
    if not segments:
        return ActionClass("T3", False, "empty command")
    result = _classify_segment(segments[0])
    for seg in segments[1:]:
        result = _more_severe(result, _classify_segment(seg))
    return result


def classify_action(
    tool: str,
    *,
    command: str | None = None,
    inside_worktree: bool = True,
) -> ActionClass:
    """Classify a proposed tool action's risk tier and auto/gate disposition.

    ``tool`` is ``"read"``, ``"edit"``, or ``"exec"``. For file tools, ``inside_worktree``
    (computed by the caller via :func:`resolve_in_worktree`) decides containment. For
    ``"exec"``, ``command`` is inspected against the boundary denylist. Unknown tools and
    anything ambiguous are up-tiered to the gate.
    """
    t = (tool or "").lower()
    if t == "read":
        if not inside_worktree:
            return ActionClass("T3", False, "read outside the worktree is not permitted")
        return ActionClass("T0", True, "read within the worktree")
    if t == "edit":
        if not inside_worktree:
            return ActionClass("T3", False, "write outside the worktree is not permitted")
        return ActionClass("T1", True, "write within the worktree feature branch")
    if t == "exec":
        return _classify_exec(command or "")
    return ActionClass("T3", False, f"unknown tool {tool!r} — gated")
