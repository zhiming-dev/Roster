"""Real tool execution against the run's worktree — read / edit / exec (spec 004, T010).

Turns a parsed :class:`~roster.protocol.ToolCall` into an actual filesystem/subprocess action
inside the sandbox (:mod:`roster.workspace`), classifies it at the boundary
(:mod:`roster.boundary`), and returns a structured :class:`ToolResult` the agent loop feeds back
and the runtime renders. Safe by construction:

* file paths are confined to the worktree (``Worktree.resolve`` → ``PathEscape`` → *denied*);
* shell commands are classified — boundary / T3+ commands are **not** auto-run, they come back
  ``gated`` for human approval (US2 turns that into an ActionProposal + suspend);
* auto commands run **shell-free** (tokenized, no shell-metacharacter interpretation) with a
  timeout, closed stdin, and a captured-output cap, so they cannot hang or flood the runtime.

Synchronous (blocking subprocess / file I/O); async callers wrap calls in ``asyncio.to_thread``
— the pattern ``store.py`` already uses. Process-group kill + output-cap tuning are hardened in
US2 (T017); this module establishes the safe seam.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, field

from .boundary import PathEscape, classify_action
from .diffutil import FileDiff, summarize_diff
from .protocol import ToolCall
from .workspace import Worktree

DEFAULT_TIMEOUT_S = 120
MAX_OUTPUT_BYTES = 64 * 1024
MAX_READ_BYTES = 256 * 1024
_TRUNC = "\n…[truncated]"


@dataclass
class ToolResult:
    """The structured outcome of one tool call — fed back to the model and emitted as events."""

    kind: str  # "read" | "edit" | "exec"
    status: str  # "ok" | "error" | "denied" | "gated"
    summary: str
    path: str | None = None
    content: str | None = None
    files: list[FileDiff] = field(default_factory=list)
    patch: str = ""
    command: str | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int | None = None
    timed_out: bool = False
    truncated: bool = False
    tier: str | None = None
    reason: str | None = None  # denial / gate / error reason

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def gated(self) -> bool:
        return self.status == "gated"

    def as_feedback(self) -> str:
        """The message fed back to the model as the next turn."""
        if self.kind == "read":
            if self.status == "ok":
                return f"[read] {self.path}\n{self.content or ''}"
            return f"[read error] {self.path}: {self.reason or self.summary}"
        if self.kind == "edit":
            if self.status == "ok":
                return f"[edit] {self.path} — {self.summary}\n{self.patch or '(no textual change)'}"
            return f"[edit error] {self.path}: {self.reason or self.summary}"
        if self.kind == "exec":
            if self.status == "gated":
                return (
                    f"[blocked] `{self.command}` needs human approval ({self.reason}). It was NOT "
                    "run. Do not retry it; continue without it or ask the Planner."
                )
            head = (
                f"[exec] $ {self.command}\n(timed out after {self.duration_ms} ms)"
                if self.timed_out
                else f"[exec] $ {self.command}\n(exit {self.exit_code}, {self.duration_ms} ms)"
            )
            parts = [head]
            if self.stdout:
                parts.append(self.stdout)
            if self.stderr:
                parts.append(f"[stderr]\n{self.stderr}")
            return "\n".join(parts)
        return f"[{self.kind}] {self.summary}"


def _as_text(x: object) -> str:
    if x is None:
        return ""
    return x.decode("utf-8", errors="replace") if isinstance(x, bytes) else str(x)


def _cap(text: str, limit: int) -> tuple[str, bool]:
    raw = text or ""
    if len(raw.encode("utf-8", errors="replace")) <= limit:
        return raw, False
    return raw[:limit] + _TRUNC, True


class ToolExecutor:
    """Executes read / edit / exec tool calls inside one run's worktree."""

    def __init__(
        self,
        worktree: Worktree,
        *,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        max_output: int = MAX_OUTPUT_BYTES,
        max_read: int = MAX_READ_BYTES,
    ) -> None:
        self.wt = worktree
        self.timeout_s = timeout_s
        self.max_output = max_output
        self.max_read = max_read

    def execute(self, call: ToolCall, *, approved: bool = False) -> ToolResult:
        """Run one tool call. ``approved`` bypasses the auto/gate check (US2 grants it post-approval)."""
        if call.error:
            return ToolResult(call.kind, "error", f"malformed {call.kind} directive", reason=call.error)
        if call.kind == "read":
            return self._read(call.path or "")
        if call.kind == "edit":
            return self._edit(call.path or "", call.body or "")
        if call.kind == "exec":
            return self._exec(call.command or "", approved=approved)
        return ToolResult(call.kind, "error", f"unknown tool {call.kind!r}")

    # -- read ------------------------------------------------------------------

    def _read(self, rel: str) -> ToolResult:
        try:
            abspath = self.wt.resolve(rel)
        except PathEscape as exc:
            return ToolResult("read", "denied", f"read denied: {rel}", path=rel, tier="T3", reason=str(exc))
        if not abspath.exists():
            return ToolResult("read", "error", f"not found: {rel}", path=rel, reason="file not found")
        if abspath.is_dir():
            return ToolResult("read", "error", f"{rel} is a directory", path=rel, reason="is a directory")
        data = abspath.read_bytes()
        truncated = len(data) > self.max_read
        text = data[: self.max_read].decode("utf-8", errors="replace") + (_TRUNC if truncated else "")
        return ToolResult(
            "read", "ok", f"read {rel} ({len(data)} bytes)", path=rel, content=text, tier="T0", truncated=truncated
        )

    # -- edit ------------------------------------------------------------------

    def _edit(self, rel: str, body: str) -> ToolResult:
        try:
            abspath = self.wt.resolve(rel)
        except PathEscape as exc:
            return ToolResult("edit", "denied", f"write denied: {rel}", path=rel, tier="T3", reason=str(exc))
        abspath.parent.mkdir(parents=True, exist_ok=True)
        abspath.write_bytes(body.encode("utf-8"))  # verbatim: preserve the model's LF, no CRLF xlate
        patch = self._file_diff(rel)
        files = summarize_diff(patch)
        summary = (
            f"{files[0].status} (+{files[0].additions} −{files[0].deletions})" if files else "no textual change"
        )
        return ToolResult("edit", "ok", summary, path=rel, files=files, patch=patch, tier="T1")

    def _file_diff(self, rel: str) -> str:
        # `add -N` records intent-to-add so a brand-new file shows in the diff; no-op if tracked.
        self._git("add", "-N", "--", rel)
        return self._git("diff", "--", rel).stdout

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(self.wt.path), *args], capture_output=True, text=True)

    def full_diff(self) -> str:
        """The cumulative change set of the worktree vs its base branch (all files, staged or not)."""
        self._git("add", "-A")
        return self._git("diff", "--cached", self.wt.base_ref).stdout

    # -- exec ------------------------------------------------------------------

    def _exec(self, command: str, *, approved: bool) -> ToolResult:
        cls = classify_action("exec", command=command)
        if not approved and not cls.auto:
            return ToolResult(
                "exec", "gated", f"needs approval: {cls.reason}", command=command, tier=cls.tier, reason=cls.reason
            )
        try:
            argv = shlex.split(command, posix=True)
        except ValueError as exc:
            return ToolResult("exec", "error", "unparseable command", command=command, reason=str(exc))
        if not argv:
            return ToolResult("exec", "error", "empty command", command=command)

        start = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                cwd=str(self.wt.path),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            dur = int((time.monotonic() - start) * 1000)
            out, _ = _cap(_as_text(exc.stdout), self.max_output)
            err, _ = _cap(_as_text(exc.stderr), self.max_output)
            return ToolResult(
                "exec", "error", f"timed out after {self.timeout_s}s", command=command,
                stdout=out, stderr=err, duration_ms=dur, timed_out=True, tier=cls.tier,
            )
        except (FileNotFoundError, OSError) as exc:
            dur = int((time.monotonic() - start) * 1000)
            return ToolResult(
                "exec", "error", f"could not run: {argv[0]}", command=command, exit_code=127,
                duration_ms=dur, reason=str(exc), tier=cls.tier,
            )

        dur = int((time.monotonic() - start) * 1000)
        out, out_trunc = _cap(proc.stdout, self.max_output)
        err, err_trunc = _cap(proc.stderr, self.max_output)
        status = "ok" if proc.returncode == 0 else "error"
        return ToolResult(
            "exec", status, f"exit {proc.returncode}", command=command, exit_code=proc.returncode,
            stdout=out, stderr=err, duration_ms=dur, truncated=out_trunc or err_trunc, tier=cls.tier,
        )
