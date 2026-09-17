"""Orchestrator — turns one principal message into a planner-led multi-agent exchange."""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import events
from .agent import Agent
from .approval import (
    PendingApproval,
    approval_summary,
    build_action_proposal,
    new_prop_id,
    parse_decision,
    record_decision,
    write_action_proposal,
)
from .bus import bus
from .config import RuntimeConfig, load_config
from .browse import BrowserFetcher
from .diffutil import summarize_diff
from .fetch import WebFetcher
from .mcptool import McpServerSpec, McpToolHost
from .protocol import parse_planner_turn
from .provenance import ProvenanceLog, new_run_id, runs_dir
from .providers import ProviderError
from .queue import LlmQueue
from .run_state import OrchestrationState, RunStatus, TurnResult
from .search import SearchProvider, build_search_provider
from .task_result import build_task_result, new_task_id, write_diff_artifact, write_task_result
from .tools import ApprovalPending, ToolExecutor
from .workspace import Worktree, WorkspaceError, WorkspaceManager

log = logging.getLogger("roster.orchestrator")


def runtime_preamble(
    *,
    can_search: bool = False,
    can_fetch: bool = False,
    can_exec: bool = False,
    has_searcher: bool = False,
) -> str:
    """A dynamic preamble prepended to every agent's system prompt.

    Two jobs: (1) tell the model what *today* is, so a model whose training data
    predates the system clock stops treating recent dates as "the future"; and
    (2) describe the agent's *actual* tool situation so it neither fabricates data
    nor — just as bad — refuses to use a tool it genuinely has.

    The tool paragraph is tailored to the agent:

    * ``can_search`` — this agent holds the web-search tool itself (its `SEARCH:`
      usage is spelled out later in the suffix). It must USE it for live facts.
    * ``can_fetch`` — this agent can also OPEN urls (`FETCH:`) and read their content.
    * ``can_exec`` — this agent has REAL file & shell tools in an isolated worktree
      (the Coder's case). It must never claim the runtime forbids running code, and
      network-touching commands are *gated for approval*, not forbidden.
    * ``has_searcher`` — this agent can't search directly but can DISPATCH to a
      specialist that can (the Planner's case).
    * none of the above — genuinely tool-less; it must say so rather than invent data.
    """
    now = _dt.datetime.now().astimezone()
    date_part = (
        "## Current context\n\n"
        f"The current date is {now:%Y-%m-%d} ({now:%A}). Treat this as *today*. "
        "Any date on or before today is in the PAST — never call a past or present "
        "date 'the future'.\n\n"
    )
    if can_search:
        fetch_clause = (
            " You ALSO have a **page-fetch tool** (`FETCH:` below) that opens one url "
            "and returns its actual content — search finds pages, FETCH reads them."
            if can_fetch
            else ""
        )
        exec_clause = (
            " You ALSO have file & shell tools in an isolated worktree (see below)."
            if can_exec
            else " You do NOT have a file system, code execution, or other live data feeds."
        )
        tools_part = (
            "You DO have a **web-search tool** in this runtime (its `SEARCH:` usage is "
            f"described below).{fetch_clause} USE it whenever a request needs live or external facts "
            "(news, market prices, weather, scores, recent events) — never claim you "
            f"lack web access.{exec_clause} Base every factual claim on actual search results and "
            "cite their URLs; if a search returns nothing or fails, say so plainly and "
            "DO NOT invent numbers, quotes, headlines, or citations."
        )
    elif can_exec:
        tools_part = (
            "You DO have REAL file & shell tools in this runtime, acting in an isolated "
            "git worktree (their READ/EDIT/EXEC usage is described below) — never claim "
            "you cannot read files, write files, or run code. You have no direct "
            "web-search tool, but shell commands MAY reach the network: commands the "
            "runtime classifies as network egress (curl, wget, pip installs from an "
            "index, etc.) PAUSE for the principal's explicit approval rather than being "
            "forbidden. When a task needs external data, PROPOSE the fetch/install "
            "command and let the approval gate decide — do NOT refuse the task upfront "
            "by claiming the runtime prohibits network access. If an approval is denied "
            "or a download fails, report exactly what you could not obtain — never "
            "fabricate data, file contents, or command output."
        )
    elif has_searcher:
        tools_part = (
            "You have no tools you invoke directly, but you CAN dispatch to specialists "
            "that have a real web-search tool (see the dispatch menu below). For any "
            "live or external fact (news, market prices, weather, scores, recent "
            "events), DISPATCH to a web-searching specialist rather than answering from "
            "memory — and never tell the principal the system 'cannot' search, because "
            "it can. Do NOT invent specific numbers, quotes, headlines, or citations "
            "yourself; let the specialist gather them."
        )
    else:
        tools_part = (
            "You have **no tools** in this runtime: no web/internet access, no file "
            "system, no code execution, no live data feeds. You therefore CANNOT look "
            "up real-time or external facts (market prices, news, weather, scores, "
            "etc.). If a request needs such data, say so plainly and DO NOT invent "
            "specific numbers, quotes, headlines, or source citations. Offer what you "
            "genuinely can do — structure, methodology, which sources the principal "
            "should consult — instead of fabricating an answer that looks real."
        )
    return date_part + tools_part


PLANNER_RUNTIME_HEAD = """\
## Runtime protocol (Roster MVP)

You are running inside the Roster runtime. You speak to the human principal directly.
The specialist sub-agents below are available; you dispatch to them when their expertise
is needed. The runtime — not you — actually invokes them.

Available specialists:
"""

# Short, accurate role blurbs for the planner's specialist list.
_ROLE_BLURBS = {
    "coder": "implements code changes on a feature branch",
}

# Richer blurbs used when the agent actually holds file/shell tools (spec 004). Without a
# workspace the coder can only *describe* changes, so the default must not overpromise.
_TOOLED_BLURBS = {
    "coder": (
        "creates and edits REAL files of any kind (code, scripts, reports, web pages, data) "
        "in an isolated workspace and runs shell commands to verify its work"
    ),
}

_ROLE_BLURBS.update({
    "e2e": "runs end-to-end browser/Playwright tests against a running build — dispatch AFTER the coder lands a change",
    "reviewer": "reviews diffs against success criteria",
    "qa": "verifies another agent's output by OPENING its cited sources and checking each claim against the page; searches only for missing/independent sources",
    "researcher": "searches the web, opens the promising pages, and synthesizes findings with source URLs",
})


@dataclass
class SpecialistCaps:
    """One specialist's entry in the planner's dispatch menu."""

    name: str
    blurb: str
    search: bool = False
    fetch: bool = False
    browse: bool = False
    calc: bool = False
    mcp: bool = False
    write: bool = False


def build_planner_suffix(specialists: list[SpecialistCaps]) -> str:
    lines = []
    for sp in specialists:
        tags = []
        if sp.search:
            tags.append("can search the web")
        if sp.fetch:
            tags.append("can open web pages/PDFs")
        if sp.browse:
            tags.append("can render JS pages")
        if sp.calc:
            tags.append("can compute")
        if sp.mcp:
            tags.append("can call external tools")
        if sp.write:
            tags.append("can write files & run commands")
        tag = f"  ← {', '.join(tags)}" if tags else ""
        lines.append(f"- `{sp.name}` — {sp.blurb}{tag}")
    has_searcher = any(sp.search for sp in specialists)
    has_writer = any(sp.write for sp in specialists)
    if has_searcher:
        web_rule = (
            "- For live or external facts (market data, news, weather, scores), dispatch "
            "to a specialist that can search the web (tagged above). Do NOT answer such "
            "questions from memory and do NOT fabricate numbers, quotes, or citations.\n"
        )
    else:
        web_rule = (
            "- None of the specialists can browse the web or fetch external data. If a "
            "goal needs live/external information, say so plainly instead of inventing "
            "it.\n"
        )
    if has_writer:
        file_rule = (
            "- Any deliverable that should exist as a FILE — a code change, script, report, "
            "web page, data file — must be dispatched to a file-writing specialist (tagged "
            "above). You cannot write files yourself; never paste would-be file contents "
            "into chat as a substitute.\n"
        )
    else:
        file_rule = ""
    return (
        PLANNER_RUNTIME_HEAD
        + "\n".join(lines)
        + """

You ORCHESTRATE; you never do the work yourself. After any brief reasoning, end your reply
with directive lines the runtime executes (no backticks):

    PLAN: <one-line summary of how you split the goal>     (optional)
    DISPATCH:<role>:<one-line task>                        (ONE line per sub-task)
    ASK: <a single question for the principal>             (only when truly blocked)

How it works:
- Decompose a non-trivial goal into the FEWEST sub-tasks that genuinely differ and emit a
  DISPATCH line for EACH — several at once. Independent dispatches run IN PARALLEL. Match each
  task to the role whose expertise fits.
- END your reply immediately after the directive lines. NEVER write a `[<role> reports]` block
  or any imagined specialist result yourself — real results are injected by the runtime as your
  next turn; writing them yourself is fabrication.
- The runtime runs them and feeds every result back as your next turn, each prefixed
  `[<role> reports]:`. Review them CRITICALLY: if a result is wrong, inconsistent, or
  unverified, DISPATCH again — to the same specialist to dig deeper, or to `qa` to fact-check —
  before you answer. After the first results return you may run up to two more rounds to verify.
- When you have enough, write the principal ONE synthesized final answer covering every part
  of their request, with NO PLAN/DISPATCH/ASK line.
- For a simple conversational message (greeting, status), just reply directly — no directives.
- Match work to the right role:
    · `researcher` gathers live/external facts: it searches, then OPENS the promising pages
      to extract real numbers and quotes — brief it to fetch sources, not to rely on snippets.
    · `qa` verifies another agent's output — brief it with the CLAIMS and their SOURCE URLS so
      it can open each source and check, rather than re-running the same searches.
    · QUANTITATIVE work — backtests, metric computations, anything needing many data points or
      math — goes to a file-writing specialist if one is tagged above: it can script the data
      pull (e.g. download a public CSV/API series) and COMPUTE real results via EXEC. Web
      search finds pages; it cannot compute. Do not ask a searching specialist to "look up"
      dozens of data points one query at a time.
    · `e2e` drives a real browser against a RUNNING build — only after `coder` lands a change.
- Diagnose failures before retrying: when a specialist comes back empty, decide WHY — unclear
  brief (fix: reword) or a tool that cannot do the job (fix: different specialist/tool, or ASK
  the principal). If a specialist failed for the same underlying reason twice, do NOT dispatch
  the same approach a third time — rewording the same brief to the same tool does not change
  the outcome.
"""
        + web_rule
        + file_rule
        + """- If a tool failed during the run (e.g. a web search was rate-limited or returned a bot
  challenge), TELL the principal what failed and the likely remedy (e.g. set TAVILY_API_KEY for a
  reliable search backend) — don't only say you couldn't verify.
- Use ASK sparingly — only when you cannot proceed safely; the runtime relays it to the
  principal and you continue once they answer.
- You never perform destructive (irreversible, T3/T4) actions yourself. If a sub-task would be
  irreversible, say so and ask the principal for explicit confirmation in chat first.
"""
    )


_SUBAGENT_HEAD = """\
## Runtime protocol (Roster MVP)

You are running inside the Roster runtime as a specialist sub-agent. The Planner has
dispatched a single task to you. Your reply goes back to the Planner, not to the human
principal. Be concise and structured:

- Restate the task in one line.
- Do the work with the tools available to you (described below). Act with real tools and
  report what they ACTUALLY returned — never describe hypothetical actions or invent results.
- Return a short, structured result the Planner can act on.
"""

_SUBAGENT_TOOLS = """\

## File & shell tools

You work inside an isolated git worktree of the target repository — a feature branch, never
`main`. To use a tool, end a reply with EXACTLY ONE directive; the runtime runs it and feeds
the result back as your next turn. Then continue, or give your final answer with no directive.

Read a file (returns its real contents):

    READ: path/to/file.py

Create or overwrite a file — put the FULL new contents in a fenced block immediately after:

    EDIT: path/to/file.py
    ```
    <the complete new file contents>
    ```

Run a shell command in the worktree (returns stdout, stderr, and the exit code):

    EXEC: pytest -q

Rules:
- EXACTLY ONE directive per reply, always as the LAST thing in it — NEVER several READs at
  once. Work stepwise: read ONE file, see its real contents next turn, then take the next step.
- Only EDIT: is followed by a fenced block (the file's FULL new contents). READ: and EXEC:
  take NOTHING after them — no code fences, no commentary below the directive line.
- Paths are relative to the worktree; you cannot read or write outside it.
- Make real changes by actually issuing EDIT — a real diff is produced from what you write.
- Boundary-crossing commands (network, `git push`, `sudo`, deleting outside the worktree)
  pause the run for the principal's approval. Your next turn shows either the command's REAL
  result (approved) or `[approval denied]` (continue without it — NEVER retry or re-propose a
  denied action). Irreversible (T4) actions are refused outright and come back `[denied]`.
- Verify your work when you can (build/tests via EXEC), and base every claim on real output.
"""

_SUBAGENT_SEARCH = """\

## Web search tool

You CAN search the web. To do so, end a reply with EXACTLY one line:

    SEARCH: <your search query>

Keep the query SHORT — 3–6 keywords, the way a person types into a search box
(e.g. `S&P 500 close June 26 2026`). Do NOT wrap it in quotation marks and do NOT
write a long full-sentence query: overly long or quoted queries reliably return
zero results.

The runtime runs the search and feeds results back as the next turn, prefixed with
`[search results]`. Then continue — search again (up to 3 times total) or write your
final answer with NO `SEARCH:` line. Base every factual claim (prices, dates, news,
numbers) ONLY on returned results and cite their URLs. If results are empty or fail,
say so — never fabricate.
"""

_SUBAGENT_FETCH = """\

## Web page fetch tool

You CAN also OPEN web pages. To fetch one url's actual content, end a reply with EXACTLY
one line:

    FETCH: <url>

The runtime downloads the page, extracts its readable text (CSV/JSON data endpoints come
back verbatim), and feeds it back as your next turn prefixed `[fetched]`. Use FETCH:

- after a SEARCH, to OPEN the promising result and read the real content instead of
  trusting a 400-character snippet;
- to pull structured data directly when you know where it lives — e.g. any FRED series
  as CSV: `FETCH: https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS`. Narrow big
  series with the endpoint's own params (FRED: `&cosd=2026-01-01` for a start date);
- to verify that a cited source actually says what a claim asserts.

A search engine returns pages, not data points — it cannot answer "what was X on date Y".
When a search result looks like it contains the answer, FETCH it (up to 6 fetches per
turn). PDFs are supported — reports, filings and papers extract to text. Long content is
truncated; cite only what you actually saw.
"""

_SUBAGENT_BROWSE = """\

## Browser render tool

Some pages are JS-rendered: FETCH returns an empty shell for them. For those, end a reply
with EXACTLY one line:

    BROWSE: <url>

The runtime loads the page in a real headless browser, lets its scripts run, and feeds
back the RENDERED text prefixed `[browsed]`. BROWSE is heavyweight (up to 3 per turn):
always try FETCH first, and BROWSE only when the fetched page came back without the
content you saw promised in search results.
"""

_SUBAGENT_CALC = """\

## Calculator tool

You CAN compute. To evaluate ONE Python expression in a sandbox, end a reply with:

    CALC: <expression>

The result comes back prefixed `[calc]`. Available: arithmetic, comparisons, list/dict
literals and comprehensions, and these functions: abs, min, max, sum, len, round, sorted,
mean, median, stdev, pstdev, variance, quantiles, correlation, sqrt, log, exp,
pct_change(old, new), drawdown([values...]). No imports, no variables, no attribute
access — paste the numbers into the expression, e.g.:

    CALC: drawdown([7650.2, 7575.4, 7391.0, 7488.8])
    CALC: pct_change(19.9, 15.84)

NEVER do arithmetic in your head for numbers that matter — CALC it (up to 8 per turn).
"""

_SUBAGENT_MCP = """\

## External tools (MCP)

This runtime is connected to external tool servers. To call one, end a reply with EXACTLY
one line — the tool name, then its arguments as a single-line JSON object (omit the JSON
when the tool takes none):

    TOOL: <tool_name> {"arg": "value"}

The result comes back prefixed `[tool <name>]`. The catalog of available tools (names,
arguments, descriptions) is listed in your system prompt once connected; call only tools
from that catalog (up to 8 calls per turn). Base claims on what the tool actually
returned.
"""

_SUBAGENT_TAIL = """\

Do NOT fabricate tool output, test results, data, or citations beyond what tools
actually returned. You have no chat with the principal — do not address them directly.
"""


def build_subagent_suffix(
    can_search: bool,
    can_use_tools: bool = False,
    can_fetch: bool = False,
    can_browse: bool = False,
    can_calc: bool = False,
    can_mcp: bool = False,
) -> str:
    parts = [_SUBAGENT_HEAD]
    if can_use_tools:
        parts.append(_SUBAGENT_TOOLS)
    if can_search:
        parts.append(_SUBAGENT_SEARCH)
    if can_fetch:
        parts.append(_SUBAGENT_FETCH)
    if can_browse:
        parts.append(_SUBAGENT_BROWSE)
    if can_calc:
        parts.append(_SUBAGENT_CALC)
    if can_mcp:
        parts.append(_SUBAGENT_MCP)
    parts.append(_SUBAGENT_TAIL)
    return "".join(parts)


_FILE_TOOL_CAPS = frozenset({"read", "edit", "execute"})


def wants_file_tools(tools: list[str]) -> bool:
    """True if an agent's grant includes any file/shell capability (spec 004)."""
    return bool(_FILE_TOOL_CAPS & {t.lower() for t in tools})


def _default_worktrees_root(target_repo: str) -> Path:
    return Path(target_repo).resolve().parent / ".roster-worktrees"

# Per principal message: one decomposition/fan-out round, then up to MAX_CRITIQUE
# critique/verification rounds, then a synthesized answer. MAX_PLANNER_TURNS is the hard
# ceiling on planner turns (fan-out + critique rounds + synthesis + slack).
MAX_PLANNER_TURNS = 6
MAX_CRITIQUE = 2


@dataclass
class DispatchOutcome:
    """One specialist dispatch's terminal state within a round.

    ``ok`` False = the specialist errored before returning a result. ``pending`` set = its
    turn is PAUSED at the approval gate (neither done nor failed) — the round suspends and
    the principal's decision resumes it.
    """

    role: str
    text: str
    ok: bool = True
    pending: PendingApproval | None = None


@dataclass
class _RoundState:
    """A dispatch round frozen mid-flight by one or more boundary approvals (US2).

    Completed siblings' results wait here while the principal decides; when every paused
    specialist has resumed and finished, the round completes and the planner sees ALL the
    results at once — exactly as if nothing had suspended.
    """

    is_critique: bool
    parts: list[str] = field(default_factory=list)  # formatted [role reports] blocks
    failed: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)  # who was dispatched this round


class Run:
    """One conversation = one run. Holds the planner + sub-agents + provenance."""

    def __init__(self, config_path: str | Path, run_id: str | None = None) -> None:
        # `run_id` is supplied when reopening a persisted conversation so the new
        # in-memory run rebinds to its existing provenance log and history.
        self.run_id = run_id or new_run_id()
        self.prov = ProvenanceLog(runs_dir(), self.run_id)
        # Orchestration state persists ACROSS principal messages so a mid-task `ASK`
        # can suspend and the next message can resume the same run.
        self.orch_state = OrchestrationState(max_critique=MAX_CRITIQUE)
        # Boundary-gate state (US2): actions paused for the principal's decision, plus the
        # dispatch round they froze. Head of the queue = the proposal currently surfaced.
        self.pending_approvals: list[PendingApproval] = []
        self._round: _RoundState | None = None
        self._surfaced_prop_id: str | None = None  # dedupes approval.requested re-emits
        # Roles dispatched so far in the CURRENT task — lets the runtime warn the planner
        # when a critique round re-runs a specialist that already had its shot (see
        # ``_complete_round``). Reset with each fresh principal message.
        self._dispatched_roles: set[str] = set()
        cfg: RuntimeConfig = load_config(config_path)

        if "planner" not in cfg.agents:
            raise RuntimeError("agents.config.yaml must define an agent named 'planner'")

        self.queue_cfg = cfg.queue
        self.llm_queue = LlmQueue(cfg.queue.max_concurrency)
        require = set(cfg.queue.require_queue)
        self.require_queue = require

        # One shared web-search backend; attached only to agents granted the tool.
        self.search_cfg = cfg.search
        self.search_provider: SearchProvider | None = build_search_provider(cfg.search)
        # One shared page fetcher (`FETCH:`); attached only to agents granted `fetch`.
        self.fetcher: WebFetcher | None = (
            WebFetcher() if any("fetch" in a.tools for a in cfg.agents.values()) else None
        )
        # One shared headless browser (`BROWSE:`); launches lazily on first use.
        self.browser: BrowserFetcher | None = (
            BrowserFetcher() if any("browse" in a.tools for a in cfg.agents.values()) else None
        )
        # One shared MCP host (`TOOL:`); connections are async — see ``init_mcp``.
        self.mcp_host: McpToolHost | None = None
        if cfg.mcp_servers and any("mcp" in a.tools for a in cfg.agents.values()):
            self.mcp_host = McpToolHost(
                [
                    McpServerSpec(name=s.name, command=s.command, args=s.args, env=s.env, cwd=s.cwd)
                    for s in cfg.mcp_servers
                ]
            )

        # Per-run workspace (spec 004): an isolated git worktree the Coder/E2E file & shell
        # tools act in. Absent/invalid/dirty target → tools are unavailable and the agent says
        # so (no fabrication) rather than the run failing.
        self.workspace_cfg = cfg.workspace
        self.workspace: WorkspaceManager | None = None
        self._worktree: Worktree | None = None
        self.workspace_error: str | None = None
        if cfg.workspace.target_repo:
            root = cfg.workspace.worktrees_root or str(
                _default_worktrees_root(cfg.workspace.target_repo)
            )
            try:
                self.workspace = WorkspaceManager(cfg.workspace.target_repo, root, self.run_id)
                self._worktree = self.workspace.create("work")
                log.info(
                    "run %s: workspace ready at %s (%s)",
                    self.run_id,
                    self._worktree.path,
                    self._worktree.branch,
                )
            except WorkspaceError as exc:
                self.workspace_error = str(exc)
                self.workspace = None
                self._worktree = None
                log.warning(
                    "run %s: workspace unavailable — file/shell tools disabled: %s",
                    self.run_id,
                    exc,
                )

        def _queue_for(name: str) -> LlmQueue | None:
            return self.llm_queue if name in require else None

        def _search_for(agent_cfg: Any) -> SearchProvider | None:
            if self.search_provider is None:
                return None
            return self.search_provider if "search" in agent_cfg.tools else None

        def _fetch_for(agent_cfg: Any) -> WebFetcher | None:
            if self.fetcher is None:
                return None
            return self.fetcher if "fetch" in agent_cfg.tools else None

        def _browse_for(agent_cfg: Any) -> BrowserFetcher | None:
            if self.browser is None:
                return None
            return self.browser if "browse" in agent_cfg.tools else None

        def _calc_for(agent_cfg: Any) -> bool:
            return "calc" in agent_cfg.tools

        def _mcp_for(agent_cfg: Any) -> McpToolHost | None:
            if self.mcp_host is None:
                return None
            return self.mcp_host if "mcp" in agent_cfg.tools else None

        def _executor_for(agent_cfg: Any) -> ToolExecutor | None:
            if self._worktree is None or not wants_file_tools(agent_cfg.tools):
                return None
            return ToolExecutor(self._worktree)

        # Specialist metadata for the planner's (dynamic) dispatch menu.
        specialists: list[SpecialistCaps] = []
        for name, agent_cfg in cfg.agents.items():
            if name == "planner":
                continue
            can_write = _executor_for(agent_cfg) is not None
            blurb = (_TOOLED_BLURBS if can_write else _ROLE_BLURBS).get(
                agent_cfg.role,
                _ROLE_BLURBS.get(
                    agent_cfg.role, (agent_cfg.description or agent_cfg.role)[:80]
                ),
            )
            specialists.append(
                SpecialistCaps(
                    name=name,
                    blurb=blurb,
                    search=_search_for(agent_cfg) is not None,
                    fetch=_fetch_for(agent_cfg) is not None,
                    browse=_browse_for(agent_cfg) is not None,
                    calc=_calc_for(agent_cfg),
                    mcp=_mcp_for(agent_cfg) is not None,
                    write=can_write,
                )
            )

        has_searcher = any(sp.search for sp in specialists)

        planner_cfg = cfg.agents["planner"]
        planner_preamble = runtime_preamble(
            can_search=_search_for(planner_cfg) is not None,
            can_fetch=_fetch_for(planner_cfg) is not None,
            has_searcher=has_searcher,
        )
        planner_suffix = planner_preamble + "\n\n" + build_planner_suffix(specialists)

        self.planner = Agent.from_config(
            planner_cfg,
            runtime_suffix=planner_suffix,
            queue=_queue_for("planner"),
            search=_search_for(planner_cfg),
            fetcher=_fetch_for(planner_cfg),
            search_max_results=cfg.search.max_results,
        )
        self.subagents: dict[str, Agent] = {}
        for name, agent_cfg in cfg.agents.items():
            if name == "planner":
                continue
            search = _search_for(agent_cfg)
            fetcher = _fetch_for(agent_cfg)
            browser = _browse_for(agent_cfg)
            calc = _calc_for(agent_cfg)
            mcp = _mcp_for(agent_cfg)
            executor = _executor_for(agent_cfg)
            self.subagents[name] = Agent.from_config(
                agent_cfg,
                runtime_suffix=(
                    runtime_preamble(
                        can_search=search is not None,
                        can_fetch=fetcher is not None,
                        can_exec=executor is not None,
                    )
                    + "\n\n"
                    + build_subagent_suffix(
                        search is not None,
                        executor is not None,
                        fetcher is not None,
                        can_browse=browser is not None,
                        can_calc=calc,
                        can_mcp=mcp is not None,
                    )
                ),
                queue=_queue_for(name),
                search=search,
                fetcher=fetcher,
                browser=browser,
                calc=calc,
                mcp=mcp,
                executor=executor,
                prov=self.prov,  # every tool action lands in provenance.jsonl (T021)
                search_max_results=cfg.search.max_results,
            )
        log.info(
            "run %s: %d agents, queue max_concurrency=%d, require_queue=%s, search=%s",
            self.run_id,
            len(cfg.agents),
            cfg.queue.max_concurrency,
            sorted(require) or "<none>",
            self.search_provider.name if self.search_provider else "disabled",
        )

    def all_agents(self) -> list[Agent]:
        return [self.planner, *self.subagents.values()]

    async def init_mcp(self) -> None:
        """Connect the configured MCP servers and inject the live tool catalog into every
        granted agent's system prompt.

        Async because MCP handshakes are; called once by the server right after the run is
        constructed. Idempotent and failure-tolerant: a dead server is skipped (logged),
        and with no catalog the granted agents simply keep their generic TOOL: section.
        """
        if self.mcp_host is None or self.mcp_host.started:
            return
        try:
            await self.mcp_host.start()
        except Exception:  # noqa: BLE001 — external servers must not kill the run
            log.warning("run %s: MCP startup failed", self.run_id, exc_info=True)
            return
        catalog = self.mcp_host.catalog_prompt()
        if not catalog:
            return
        for agent in self.all_agents():
            if agent.mcp is None:
                continue
            if agent.history and agent.history[0].get("role") == "system":
                agent.history[0]["content"] += "\n\n---\n\n" + catalog
        log.info(
            "run %s: MCP connected — %d tools from %d server(s)%s",
            self.run_id,
            len(self.mcp_host.tools),
            len(self.mcp_host._specs) - len(self.mcp_host.errors),
            f" ({len(self.mcp_host.errors)} failed)" if self.mcp_host.errors else "",
        )

    def resume_from_events(self, events: list[dict[str, Any]]) -> None:
        """Seed the planner's chat history from a persisted conversation so it can
        continue where it left off.

        Only the principal⇄planner transcript is restored — sub-agent histories are
        ephemeral and start fresh (acceptable for this MVP). Each prior principal
        message becomes a ``user`` turn and each final planner reply an ``assistant``
        turn, preserving the system prompt already at ``history[0]``.
        """
        for e in events:
            kind = e.get("kind")
            if kind == "user.message":
                content = str(e.get("content") or "")
                if content:
                    self.planner.history.append({"role": "user", "content": content})
            elif (
                kind == "agent.message"
                and e.get("to") == "principal"
                and e.get("subkind", "message") == "message"
            ):
                content = str(e.get("content") or "")
                if content:
                    self.planner.history.append(
                        {"role": "assistant", "content": content}
                    )

    def queue_stats(self) -> dict[str, Any]:
        st = self.llm_queue.stats()
        return {
            "max_concurrency": st.max_concurrency,
            "waiting": st.waiting,
            "active": st.active,
            "require_queue": sorted(self.require_queue),
            "search": self.search_provider.name if self.search_provider else None,
        }

    async def aclose(self) -> None:
        for a in self.all_agents():
            try:
                await a.provider.aclose()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                log.debug("provider aclose failed for agent %s", a.cfg.name, exc_info=True)
        if self.search_provider is not None:
            try:
                await self.search_provider.aclose()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                log.debug("search provider aclose failed", exc_info=True)
        if self.fetcher is not None:
            try:
                await self.fetcher.aclose()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                log.debug("fetcher aclose failed", exc_info=True)
        if self.browser is not None:
            try:
                await self.browser.aclose()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                log.debug("browser aclose failed", exc_info=True)
        if self.mcp_host is not None:
            try:
                await self.mcp_host.aclose()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                log.debug("mcp host aclose failed", exc_info=True)

    async def health(self) -> list[dict[str, Any]]:
        return [await a.health() for a in self.all_agents()]

    async def _publish_message(
        self, src: str, dst: str, content: str, subkind: str = "message"
    ) -> None:
        await bus.publish(
            "agent.message",
            subkind=subkind,
            **{"from": src, "to": dst, "content": content},
        )

    async def _run_dispatch(self, role: str, task: str, round_idx: int) -> DispatchOutcome:
        """Dispatch one task to a specialist and return its :class:`DispatchOutcome`.

        Safe to gather(): a specialist failure (provider error, content filter, timeout) is
        returned as a RESULT with ok=False — never raised — so one blocked specialist cannot
        abort its siblings' work or the planner's turn. The planner decides how to recover.
        A boundary-gated tool call likewise comes back as an outcome (``pending`` set): the
        specialist's turn stays paused while its siblings run to completion.
        """
        await self._publish_message("planner", role, task, subkind="task_assignment")
        self.prov.emit("task.dispatched", actor="planner", to=role, task=task, round=round_idx)
        await events.emit_task_dispatched(to=role, task=task, round=round_idx)
        subagent = self.subagents[role]
        try:
            sub_reply = await subagent.chat(task)
        except ApprovalPending as ap:
            pending = await self._register_pending(subagent, ap)
            return DispatchOutcome(role=role, text="", pending=pending)
        except Exception as exc:  # noqa: BLE001 — surfaced to the planner, not swallowed
            reason = str(exc) if isinstance(exc, ProviderError) else f"{type(exc).__name__}: {exc}"
            reason = " ".join(reason.split())[:400]
            log.warning("run %s: dispatch to %s failed: %s", self.run_id, role, reason)
            self.prov.emit(
                "task.failed", actor=role, model=subagent.cfg.provider.target, error=reason
            )
            await self._publish_message(role, "planner", f"[failed] {reason}", subkind="task_result")
            return DispatchOutcome(role=role, text=reason, ok=False)
        await self._record_task_result(subagent, sub_reply)
        return DispatchOutcome(role=role, text=sub_reply)

    async def _record_task_result(self, subagent: Agent, sub_reply: str) -> None:
        """Provenance + artifacts + the task_result message for one completed specialist turn."""
        role = subagent.cfg.name
        self.prov.emit(
            "task.result", actor=role, model=subagent.cfg.provider.target, content=sub_reply
        )
        if subagent.executor is not None:
            try:
                await self._finalize_tool_result(subagent, sub_reply)
            except Exception:  # noqa: BLE001 — artifact capture must not void a real result
                log.warning(
                    "run %s: artifact capture for %s failed", self.run_id, role, exc_info=True
                )
        await self._publish_message(role, "planner", sub_reply, subkind="task_result")

    async def _finalize_tool_result(self, subagent: Agent, sub_reply: str) -> None:
        """Capture a tool-using specialist's change set: write ``diff.patch`` + a schema-valid
        ``TaskResult``, emit the final diff event, and record provenance (spec 004, T014)."""
        assert subagent.executor is not None
        task_id = new_task_id()
        patch = await asyncio.to_thread(subagent.executor.full_diff)
        runs = runs_dir()
        write_diff_artifact(runs, self.run_id, task_id, patch)
        files = summarize_diff(patch)
        result = build_task_result(
            task_id=task_id,
            run_id=self.run_id,
            completed_by=subagent.cfg.name,
            summary=sub_reply.strip()[:500],
            patch=patch,
        )
        write_task_result(runs, self.run_id, result)
        if files:
            await events.emit_tool_file(
                subagent.cfg.name, "diff", files=[asdict(f) for f in files], patch=patch
            )
        self.prov.emit(
            "task.result.artifact",
            actor=subagent.cfg.name,
            taskId=task_id,
            artifact=f"artifacts/{task_id}/diff.patch",
            filesChanged=len(files),
            additions=sum(f.additions for f in files),
            deletions=sum(f.deletions for f in files),
        )

    # ---- boundary approval gate (spec 004, US2) ---------------------------------

    async def _register_pending(self, subagent: Agent, ap: ApprovalPending) -> PendingApproval:
        """Turn a gated tool call into a persisted ActionProposal (+ provenance record).

        The live ``approval.requested`` bus event fires when the proposal is *surfaced*
        (``_surface_approval``) — the UI's "current decidable proposal" then always tracks
        the head of the queue, even when several actions gate in one round.
        """
        pending = PendingApproval(
            prop_id=new_prop_id(),
            agent=subagent.cfg.name,
            role=subagent.cfg.role,
            call=ap.call,
            tier=ap.result.tier or "T3",
            reason=ap.result.reason or "boundary-crossing action",
        )
        proposal = build_action_proposal(pending, self.run_id)
        write_action_proposal(runs_dir(), self.run_id, proposal)
        self.prov.emit(
            "approval.requested",
            actor=pending.agent,
            propId=pending.prop_id,
            tier=pending.tier,
            command=pending.call.command,
            reason=pending.reason,
        )
        return pending

    async def _surface_approval(self, pending: PendingApproval) -> TurnResult:
        """Show the head proposal to the principal and hold the run in awaiting_input."""
        if pending.prop_id != self._surfaced_prop_id:
            self._surfaced_prop_id = pending.prop_id
            await events.emit_approval_requested(
                agent=pending.agent,
                prop_id=pending.prop_id,
                tier=pending.tier,
                action=pending.action_text,
                summary=pending.reason,
            )
        question = approval_summary(pending)
        await self._publish_message(pending.agent, "principal", question)
        self.orch_state.suspend(RunStatus.DISPATCHING)
        return TurnResult(status="awaiting_input", text=question)

    async def _handle_approval_decision(self, user_text: str) -> TurnResult:
        """Route the principal's chat message while a proposal is surfaced.

        Only an explicit approve/reject counts (constitution I); anything ambiguous
        re-surfaces the proposal rather than guessing at consent.
        """
        pending = self.pending_approvals[0]
        decision = parse_decision(user_text)
        if decision is None:
            question = (
                "I need an explicit decision on the pending action before the task can "
                "continue.\n\n" + approval_summary(pending)
            )
            await self._publish_message(pending.agent, "principal", question)
            return TurnResult(status="awaiting_input", text=question)
        return await self._apply_decision(pending, decision)

    async def _apply_decision(self, pending: PendingApproval, decision: str) -> TurnResult:
        """Execute (approve) or abandon (reject) the gated action, resume the paused
        specialist's turn, and — once no approvals remain — complete the frozen round."""
        self.pending_approvals.pop(0)
        self._surfaced_prop_id = None
        record_decision(runs_dir(), self.run_id, pending.prop_id, decision)
        resolved = "approved" if decision == "approve" else "rejected"
        await events.emit_approval_resolved(pending.prop_id, resolved)
        self.prov.emit(
            "approval.resolved", actor="principal", propId=pending.prop_id, decision=decision
        )

        subagent = self.subagents[pending.agent]
        role = pending.agent
        if decision == "approve" and subagent.executor is not None:
            result = await asyncio.to_thread(
                subagent.executor.execute, pending.call, approved=True
            )
            await subagent._emit_tool_events(result)
            feedback = result.as_feedback()
        else:
            feedback = (
                f"[approval denied] The principal rejected `{pending.action_text}`. Do NOT "
                "retry or re-propose it. Continue the task without it, or state plainly what "
                "you cannot complete because of it."
            )

        try:
            sub_reply = await subagent.resume_turn(feedback)
        except ApprovalPending as ap:
            # The same specialist hit the boundary again — surface the new proposal at the
            # head of the queue (its turn is still the one in flight).
            new_pending = await self._register_pending(subagent, ap)
            self.pending_approvals.insert(0, new_pending)
            return await self._surface_approval(new_pending)
        except Exception as exc:  # noqa: BLE001 — a failure is a result, not a crash
            reason = str(exc) if isinstance(exc, ProviderError) else f"{type(exc).__name__}: {exc}"
            reason = " ".join(reason.split())[:400]
            log.warning("run %s: resume of %s failed: %s", self.run_id, role, reason)
            self.prov.emit(
                "task.failed", actor=role, model=subagent.cfg.provider.target, error=reason
            )
            await self._publish_message(role, "planner", f"[failed] {reason}", subkind="task_result")
            if self._round is not None:
                self._round.parts.append(f"[{role} FAILED to deliver]: {reason}")
                self._round.failed.append(role)
        else:
            await self._record_task_result(subagent, sub_reply)
            if self._round is not None:
                self._round.parts.append(f"[{role} reports]:\n{sub_reply}")

        if self.pending_approvals:
            return await self._surface_approval(self.pending_approvals[0])

        round_state = self._round or _RoundState(is_critique=self.orch_state.gathered)
        self._round = None
        next_input = self._complete_round(round_state)
        self.orch_state.resume()
        return await self._planner_loop(next_input)

    def has_pending_approval(self, prop_id: str) -> bool:
        """True when ``prop_id`` is the currently-surfaced (decidable) proposal."""
        return bool(self.pending_approvals) and self.pending_approvals[0].prop_id == prop_id

    async def resolve_approval(self, prop_id: str, decision: str) -> TurnResult:
        """T019 sugar: decide the surfaced proposal by id (``approve`` / ``reject``)."""
        if not self.has_pending_approval(prop_id):
            raise KeyError(f"no surfaced approval with id '{prop_id}'")
        if decision not in ("approve", "reject"):
            raise ValueError("decision must be 'approve' or 'reject'")
        return await self._apply_decision(self.pending_approvals[0], decision)

    # ---- the planner loop --------------------------------------------------------

    def _complete_round(self, rs: _RoundState) -> str:
        """Apply a finished dispatch round's bookkeeping and build the planner's next input."""
        if rs.is_critique:
            self.orch_state.note_critique()
        else:
            self.orch_state.gathered = True

        # Failure attribution: a critique round that re-ran an already-dispatched specialist
        # is a RETRY. Remind the planner that a retry that fails the same way means the tool
        # (not the wording) is the problem — escalate, don't re-reword.
        repeated = (
            sorted(set(rs.roles) & self._dispatched_roles) if rs.is_critique else []
        )
        self._dispatched_roles.update(rs.roles)

        parts = list(rs.parts)
        if rs.unknown:
            parts.append(f"[runtime] Unknown specialist(s) ignored: {', '.join(rs.unknown)}.")
        next_input = "\n\n".join(parts)

        if repeated:
            next_input += (
                f"\n\n[runtime] This round RE-dispatched {', '.join(repeated)} — they already "
                "ran earlier in this task. If a result above is still inadequate for the SAME "
                "underlying reason as before (e.g. its tool simply cannot reach the data), do "
                "NOT retry the same approach again: switch to a specialist with different "
                "tools (e.g. one that can open pages or script a data pull and compute via "
                "shell), or ASK the principal how to proceed. Rewording the same brief to the "
                "same tool does not change the outcome."
            )

        if rs.failed:
            next_input += (
                f"\n\n[runtime] {', '.join(rs.failed)} failed before returning a result "
                "(a provider/tool error — the task itself may be fine). Recovery is YOUR "
                "job, not the principal's: re-DISPATCH (same specialist, a reworded task, "
                "or a different role), or — if you must answer without it — say plainly "
                "what failed and what is therefore unverified. NEVER invent what the "
                "failed specialist would have said."
            )

        # Critique nudge: make the planner vet the results before it answers.
        if self.orch_state.can_critique():
            remaining = self.orch_state.max_critique - self.orch_state.critique_used
            next_input += (
                "\n\n[runtime] Now CRITICALLY evaluate these results for consistency, "
                "plausibility, and completeness. If a factual claim needs independent "
                "confirmation, DISPATCH `qa` to verify it; if a result is wrong, empty, or "
                "incomplete, re-DISPATCH the specialist with sharper instructions — "
                "recovering from a weak result is YOUR job, never the principal's (do NOT "
                "ask them to resend or retry). If everything checks out, write the final "
                f"synthesized answer with no directives. ({remaining} critique round(s) left.)"
            )
        else:
            next_input += (
                "\n\n[runtime] Critique budget reached. Write the principal ONE synthesized "
                "final answer now covering every part of the request, explicitly flagging "
                "any unresolved uncertainty — with no DISPATCH or ASK line."
            )
        return next_input

    async def handle_principal_message(self, user_text: str) -> TurnResult:
        # A run paused at the approval gate treats THIS message as the decision; a run paused
        # on a planner clarification treats it as the answer. Otherwise it starts fresh.
        awaiting_approval = self.orch_state.awaiting_input and bool(self.pending_approvals)
        resuming_ask = self.orch_state.awaiting_input and not awaiting_approval

        await bus.publish(
            "user.message", **{"from": "principal", "to": "planner", "content": user_text}
        )
        self.prov.emit("principal.message", actor="principal", content=user_text)

        if awaiting_approval:
            return await self._handle_approval_decision(user_text)

        if resuming_ask:
            await events.emit_clarification_answered(user_text)
            self.prov.emit("clarification.answered", actor="principal", answer=user_text)
            self.orch_state.resume()
            next_input = f"[principal answers]: {user_text}\n\nContinue the task."
        else:
            self.orch_state.reset()
            self._dispatched_roles = set()  # a fresh task — retry tracking starts over
            next_input = user_text

        return await self._planner_loop(next_input)

    async def _planner_loop(self, next_input: str) -> TurnResult:
        for turn_idx in range(MAX_PLANNER_TURNS):
            reply = await self.planner.chat(next_input)
            self.prov.emit(
                "planner.reply",
                actor="planner",
                turn=turn_idx,
                model=self.planner.cfg.provider.target,
                content=reply,
            )
            turn = parse_planner_turn(reply)

            # 1) Mid-task clarification: ask the principal and SUSPEND. The next message
            #    resumes this same run (the planner's history + orchestration state persist).
            if turn.ask is not None:
                if turn.prose:
                    await self._publish_message(
                        "planner", "principal", turn.prose, subkind="thinking"
                    )
                await self._publish_message("planner", "principal", turn.ask)
                await events.emit_clarification_requested(turn.ask)
                self.prov.emit("clarification.requested", actor="planner", question=turn.ask)
                resume_phase = (
                    RunStatus.CRITIQUING if self.orch_state.gathered else RunStatus.PLANNING
                )
                self.orch_state.suspend(resume_phase)
                return TurnResult(status="awaiting_input", text=turn.ask)

            # 2) No directives → the planner's final answer to the principal.
            if not turn.dispatches:
                answer = turn.prose or reply
                await self._publish_message("planner", "principal", answer)
                self.orch_state.reset()
                return TurnResult(status="done", text=answer)

            # 3) The planner wants to dispatch. The first dispatching turn is the
            #    decomposition/fan-out; every later one is a critique/verification round
            #    (the planner pushing back on a result before it answers).
            is_critique = self.orch_state.gathered
            if is_critique and not self.orch_state.can_critique():
                next_input = (
                    "[runtime] Critique budget reached — do NOT dispatch again. Write the "
                    "best-effort final answer now and explicitly flag any unresolved "
                    "uncertainty (no DISPATCH/ASK line)."
                )
                continue

            # Models occasionally emit the same DISPATCH line twice; running both doubles
            # the cost and invites rate limits, so identical (role, task) pairs collapse.
            deduped: list[tuple[str, str]] = []
            for pair in turn.dispatches:
                if pair not in deduped:
                    deduped.append(pair)
            if len(deduped) < len(turn.dispatches):
                log.info(
                    "run %s: dropped %d duplicate dispatch line(s)",
                    self.run_id,
                    len(turn.dispatches) - len(deduped),
                )
            valid = [(r, t) for (r, t) in deduped if r in self.subagents]
            unknown = [r for (r, _t) in deduped if r not in self.subagents]

            if turn.prose:
                await self._publish_message("planner", "principal", turn.prose, subkind="thinking")

            if not is_critique:
                if turn.plan_summary or len(turn.dispatches) > 1:
                    tasks_payload = [{"role": r, "task": t} for (r, t) in turn.dispatches]
                    await events.emit_plan_proposed(
                        self.run_id, turn.plan_summary or "", tasks_payload
                    )
                    self.prov.emit(
                        "plan.proposed",
                        actor="planner",
                        summary=turn.plan_summary or "",
                        tasks=tasks_payload,
                    )
            else:
                # The planner is pushing back on a prior result — record the critique.
                targets = [r for (r, _t) in valid]
                concern = turn.prose or turn.plan_summary or "a prior result needs checking"
                action = "verify" if any(r in ("qa", "reviewer") for r in targets) else "re-dispatch"
                round_no = self.orch_state.critique_used + 1
                await events.emit_critique_round(
                    round=round_no, concern=concern, action=action,
                    to=targets[0] if targets else None,
                )
                self.prov.emit(
                    "critique.round", actor="planner", round=round_no,
                    concern=concern, action=action, to=targets[0] if targets else None,
                )

            if not valid:
                next_input = (
                    f"[runtime] Unknown specialist(s): {', '.join(unknown)}. "
                    f"Available: {', '.join(self.subagents)}."
                )
                self.prov.emit("dispatch.invalid", actor="runtime", roles=unknown)
                continue

            # Independent dispatches run concurrently (governed by the LLM queue's
            # max_concurrency; raise it for agents on separate/cloud backends).
            round_idx = self.orch_state.critique_used if is_critique else 0
            outcomes = await asyncio.gather(
                *(self._run_dispatch(r, t, round_idx) for (r, t) in valid)
            )

            round_state = _RoundState(
                is_critique=is_critique,
                parts=[
                    f"[{o.role} reports]:\n{o.text}" if o.ok else f"[{o.role} FAILED to deliver]: {o.text}"
                    for o in outcomes
                    if o.pending is None
                ],
                failed=[o.role for o in outcomes if not o.ok],
                unknown=list(unknown),
                roles=[r for (r, _t) in valid],
            )

            # One or more specialists stopped at the approval gate: freeze the round (their
            # siblings' finished work waits in it) and hand the decision to the principal.
            pendings = [o.pending for o in outcomes if o.pending is not None]
            if pendings:
                self.pending_approvals.extend(pendings)
                self._round = round_state
                return await self._surface_approval(self.pending_approvals[0])

            next_input = self._complete_round(round_state)

        final_reply = (
            "[runtime] The planner did not converge on a final answer within the round "
            "budget. Please re-prompt or simplify the request."
        )
        await self._publish_message("planner", "principal", final_reply)
        self.prov.emit("turn.budget_exhausted", actor="runtime")
        self.orch_state.reset()
        return TurnResult(status="done", text=final_reply)
