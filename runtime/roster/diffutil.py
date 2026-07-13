"""Summarize a unified ``git diff`` into a per-file changeset (spec 004, T005).

Pure (stdlib only) so it is unit-testable without git: the runtime runs ``git diff`` in the
worktree and passes its text here to build the ``tool.file`` ``diff`` event payload and the
frontend's per-file headers (path · status · +additions / −deletions).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DIFF_GIT_RE = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+)$")


@dataclass(frozen=True)
class FileDiff:
    """One file's change summary within a diff."""

    path: str
    status: str  # "added" | "modified" | "deleted" | "renamed"
    additions: int
    deletions: int


def _strip_ab(s: str) -> str:
    s = s.strip()
    if "\t" in s:  # some diffs append a tab + timestamp
        s = s.split("\t", 1)[0]
    if s == "/dev/null":
        return s
    if s.startswith(("a/", "b/")):
        s = s[2:]
    return s


def _resolve_path(f: dict) -> str:
    new, old = f.get("new"), f.get("old")
    if f["status"] == "deleted":
        return old if old and old != "/dev/null" else f["path"]
    if new and new != "/dev/null":
        return new
    if old and old != "/dev/null":
        return old
    return f["path"]


def summarize_diff(patch: str) -> list[FileDiff]:
    """Parse unified ``git diff`` text into a list of per-file summaries (order preserved)."""
    files: list[dict] = []
    cur: dict | None = None

    for line in (patch or "").splitlines():
        m = _DIFF_GIT_RE.match(line)
        if m is not None:
            cur = {
                "path": m.group("b").strip(),
                "status": "modified",
                "add": 0,
                "del": 0,
                "old": None,
                "new": None,
            }
            files.append(cur)
            continue
        if cur is None:
            continue

        if line.startswith("new file mode"):
            cur["status"] = "added"
        elif line.startswith("deleted file mode"):
            cur["status"] = "deleted"
        elif line.startswith("rename from "):
            cur["status"] = "renamed"
            cur["old"] = line[len("rename from ") :].strip()
        elif line.startswith("rename to "):
            cur["status"] = "renamed"
            cur["new"] = line[len("rename to ") :].strip()
        elif line.startswith("--- "):
            cur["old"] = _strip_ab(line[4:])
        elif line.startswith("+++ "):
            cur["new"] = _strip_ab(line[4:])
        elif line.startswith("@@"):
            continue
        elif line.startswith("+"):
            cur["add"] += 1
        elif line.startswith("-"):
            cur["del"] += 1

    return [
        FileDiff(path=_resolve_path(f), status=f["status"], additions=f["add"], deletions=f["del"])
        for f in files
    ]
