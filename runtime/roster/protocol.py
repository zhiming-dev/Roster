"""Planner turn protocol.

The planner ends a turn with zero or more *directive* lines that the runtime executes:

    PLAN: <one-line decomposition summary>     (optional)
    DISPATCH:<role>:<one-line task>            (one PER sub-task; several = parallel fan-out)
    ASK: <a single question for the principal> (suspend and clarify)

Everything that is not a directive line is the planner's prose (a brief thought before a
dispatch, or the final answer when there are no directives). This module is pure (stdlib
only) so it can be unit-tested without a live model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DISPATCH_RE = re.compile(
    r"^\s*DISPATCH\s*:\s*(?P<role>[a-z_][a-z0-9_-]*)\s*:\s*(?P<task>.+?)\s*$",
    re.IGNORECASE,
)
ASK_RE = re.compile(r"^\s*ASK\s*:\s*(?P<q>.+?)\s*$", re.IGNORECASE)
PLAN_RE = re.compile(r"^\s*PLAN\s*:\s*(?P<s>.+?)\s*$", re.IGNORECASE)


@dataclass
class PlannerTurn:
    """One parsed planner reply."""

    plan_summary: str | None = None
    dispatches: list[tuple[str, str]] = field(default_factory=list)  # (role, task)
    ask: str | None = None
    prose: str = ""  # the reply minus directive lines


def parse_planner_turn(reply: str) -> PlannerTurn:
    plan_summary: str | None = None
    dispatches: list[tuple[str, str]] = []
    ask: str | None = None
    prose_lines: list[str] = []

    for line in reply.splitlines():
        m_dispatch = DISPATCH_RE.match(line)
        m_ask = ASK_RE.match(line)
        m_plan = PLAN_RE.match(line)
        if m_dispatch:
            dispatches.append((m_dispatch.group("role").lower(), m_dispatch.group("task").strip()))
        elif m_ask and ask is None:
            ask = m_ask.group("q").strip()
        elif m_plan and plan_summary is None:
            plan_summary = m_plan.group("s").strip()
        else:
            prose_lines.append(line)

    # Asking the principal takes precedence: hold any dispatches until they answer.
    if ask is not None:
        dispatches = []

    return PlannerTurn(
        plan_summary=plan_summary,
        dispatches=dispatches,
        ask=ask,
        prose="\n".join(prose_lines).strip(),
    )


def is_final(turn: PlannerTurn) -> bool:
    """True when the turn carries no directives — i.e. it's the answer to the principal."""
    return turn.ask is None and not turn.dispatches


# --- subagent tool-call protocol (spec 004) ----------------------------------
#
# A specialist ends a reply with EXACTLY one trailing tool directive that the runtime
# executes, then feeds the result back — the same parse→act→feed-back loop the web-search
# `SEARCH:` directive already uses, generalized to file/shell tools:
#
#     READ: <relative-path>          (return real file contents)
#     EXEC: <command>                (run in the run's worktree)
#     EDIT: <relative-path>          (write the file; the new contents follow as a fenced block)
#     ```
#     <new file contents>
#     ```
#
# The parser is pure: it recognizes the directive but never touches the filesystem. A directive
# that is present but malformed returns a ToolCall with ``error`` set, so the runtime can send a
# corrective message instead of mistaking it for a final answer.

# EDIT: <path> followed by a fenced code block that ends the reply. The body captures whole
# lines *including* their trailing newline (so a file keeps its final newline); MULTILINE lets
# the EDIT line follow prose; anchored to end (\Z) so it's the trailing block.
_EDIT_BLOCK_RE = re.compile(
    r"^[ \t]*EDIT[ \t]*:[ \t]*(?P<path>[^\n]*?)[ \t]*\n+```[^\n]*\n(?P<body>(?:.*\n)*?)```[ \t]*\Z",
    re.IGNORECASE | re.MULTILINE,
)
_READ_RE = re.compile(r"^\s*READ\s*:\s*(?P<path>.*)$", re.IGNORECASE)
_EXEC_RE = re.compile(r"^\s*EXEC\s*:\s*(?P<cmd>.*)$", re.IGNORECASE)
_EDIT_LINE_RE = re.compile(r"^\s*EDIT\s*:\s*(?P<path>.*)$", re.IGNORECASE)


@dataclass
class ToolCall:
    """One parsed subagent tool directive.

    ``kind`` is ``read`` | ``edit`` | ``exec``. ``error`` is set (with ``kind`` still populated)
    when a directive was clearly intended but is malformed — the runtime feeds ``error`` back as
    a corrective message rather than executing an ambiguous action.
    """

    kind: str
    path: str | None = None
    body: str | None = None
    command: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _clean_path(p: str) -> str:
    """Trim whitespace and a single layer of surrounding quotes/backticks a model may add."""
    p = p.strip()
    if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'`":
        p = p[1:-1].strip()
    return p


def parse_tool_call(reply: str) -> ToolCall | None:
    """Parse a specialist reply's trailing tool directive.

    Returns ``None`` when the reply carries no directive (it's a final answer), a valid
    ``ToolCall`` when it does, or a ``ToolCall`` with ``error`` set when a directive is present
    but malformed. Pure — no filesystem access.
    """
    if not reply or not reply.strip():
        return None

    # EDIT with a fenced body is the only multi-line directive — check it first, anchored to end.
    m_edit = _EDIT_BLOCK_RE.search(reply)
    if m_edit is not None:
        path = _clean_path(m_edit.group("path"))
        if not path:
            return ToolCall("edit", error="EDIT: requires a file path before the code block")
        return ToolCall("edit", path=path, body=m_edit.group("body"))

    # Otherwise the directive, if any, is the last non-empty line (like SEARCH:).
    last = next((ln for ln in reversed(reply.splitlines()) if ln.strip()), "")

    m = _EDIT_LINE_RE.match(last)
    if m is not None:
        return ToolCall(
            "edit",
            path=_clean_path(m.group("path")) or None,
            error="EDIT: must be followed by a fenced code block with the file's new contents",
        )

    m = _READ_RE.match(last)
    if m is not None:
        path = _clean_path(m.group("path"))
        if not path:
            return ToolCall("read", error="READ: requires a file path")
        return ToolCall("read", path=path)

    m = _EXEC_RE.match(last)
    if m is not None:
        command = m.group("cmd").strip()
        if not command:
            return ToolCall("exec", error="EXEC: requires a command")
        return ToolCall("exec", command=command)

    return None
