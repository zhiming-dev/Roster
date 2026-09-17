"""Live agent: an agent definition (.agent.md) bound to a provider, with chat history,
an observable status, optional routing through the shared LLM queue, and an optional
web-search tool loop.

Status lifecycle: ``idle`` → (``queued`` →) ``thinking`` → (``searching`` | ``fetching`` |
``working`` → ``thinking`` …) → ``idle`` | ``error`` | ``blocked``. ``queued`` appears only for
agents in ``queue.require_queue`` when the queue is contended; ``searching``/``fetching`` appear
while a web query/page fetch is in flight; ``working`` appears while a file/shell tool
(spec 004) runs; ``blocked`` marks a turn paused at the approval gate (US2) until the
principal decides.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from . import events
from .bus import bus
from .config import AgentConfig
from .browse import BrowserFetcher
from .calc import CalcError, evaluate as calc_evaluate
from .fetch import FetchError, WebFetcher, format_fetch_result
from .mcptool import McpError, McpToolHost, parse_tool_args
from .protocol import ToolCall, has_directive_lines, parse_tool_call
from .providers import Provider, ProviderError, build_provider
from .queue import LlmQueue, QueueStats
from .search import SearchError, SearchProvider, format_results
from .tools import ApprovalPending, ToolExecutor, ToolResult

log = logging.getLogger("roster.agent")

# Tool calls the model emits as the LAST line of a reply, mirroring DISPATCH:.
SEARCH_RE = re.compile(r"^\s*SEARCH\s*:\s*(?P<query>.+?)\s*$", re.IGNORECASE)
FETCH_RE = re.compile(r"^\s*FETCH\s*:\s*(?P<url>.+?)\s*$", re.IGNORECASE)
BROWSE_RE = re.compile(r"^\s*BROWSE\s*:\s*(?P<url>.+?)\s*$", re.IGNORECASE)
CALC_RE = re.compile(r"^\s*CALC\s*:\s*(?P<expr>.+?)\s*$", re.IGNORECASE)
MCP_RE = re.compile(
    r"^\s*TOOL\s*:\s*(?P<name>[A-Za-z0-9_.\-]+)\s*(?P<args>\{.*\})?\s*$", re.IGNORECASE
)

# Transient provider failures (429 rate limits, timeouts, 5xx) are retried with backoff
# instead of failing the specialist's whole task. 4 attempts ≈ up to ~30s of patience.
MAX_LLM_ATTEMPTS = 4
_RETRY_BASE_DELAY_S = 3.0
_RETRY_MAX_DELAY_S = 30.0

MAX_SEARCHES_PER_TURN = 3
# Fetches are cheap and precise (one url each) — a verifier opening several cited sources
# needs more of them than it needs fresh queries.
MAX_FETCHES_PER_TURN = 6
MAX_BROWSES_PER_TURN = 3  # a full Chromium render each — heavier than FETCH
MAX_CALCS_PER_TURN = 8  # sandboxed expressions are nearly free
MAX_MCP_CALLS_PER_TURN = 8
# Total tool directives (read/edit/exec + search) the runtime runs in one turn before forcing a
# final answer. Generous for a coder (read a few files, edit, run tests, fix), but bounded.
MAX_TOOL_CALLS_PER_TURN = 16


@dataclass
class Agent:
    cfg: AgentConfig
    provider: Provider
    queue: LlmQueue | None = None  # set when this agent must serialize through the queue
    search: SearchProvider | None = None  # set when this agent has the `search` tool
    fetcher: WebFetcher | None = None  # set when this agent has the `fetch` tool
    browser: BrowserFetcher | None = None  # set when this agent has the `browse` tool
    calc: bool = False  # True when this agent has the sandboxed `calc` tool
    mcp: McpToolHost | None = None  # set when this agent has the `mcp` (TOOL:) grant
    executor: ToolExecutor | None = None  # set when this agent has file/shell tools (spec 004)
    prov: Any | None = None  # the run's ProvenanceLog; every tool action lands there (T021)
    search_max_results: int = 5
    history: list[dict[str, str]] = field(default_factory=list)
    status: str = "idle"  # idle | queued | thinking | searching | fetching | working | blocked | error
    queue_waiting: int = 0

    @classmethod
    def from_config(
        cls,
        cfg: AgentConfig,
        runtime_suffix: str = "",
        queue: LlmQueue | None = None,
        search: SearchProvider | None = None,
        fetcher: WebFetcher | None = None,
        browser: BrowserFetcher | None = None,
        calc: bool = False,
        mcp: McpToolHost | None = None,
        search_max_results: int = 5,
        executor: ToolExecutor | None = None,
        prov: Any | None = None,
    ) -> "Agent":
        system = cfg.system_prompt
        if cfg.skills_prompt:
            system = system + "\n\n---\n\n## Skills you have\n\n" + cfg.skills_prompt
        if runtime_suffix:
            system = system + "\n\n---\n\n" + runtime_suffix
        return cls(
            cfg=cfg,
            provider=build_provider(cfg.provider),
            queue=queue,
            search=search,
            fetcher=fetcher,
            browser=browser,
            calc=calc,
            mcp=mcp,
            executor=executor,
            prov=prov,
            search_max_results=search_max_results,
            history=[{"role": "system", "content": system}],
        )

    @property
    def queued_enabled(self) -> bool:
        return self.queue is not None

    @property
    def search_enabled(self) -> bool:
        return self.search is not None

    @property
    def fetch_enabled(self) -> bool:
        return self.fetcher is not None

    @property
    def browse_enabled(self) -> bool:
        return self.browser is not None

    @property
    def mcp_enabled(self) -> bool:
        return self.mcp is not None

    @property
    def tools_enabled(self) -> bool:
        return self.executor is not None

    async def _set_status(self, status: str, **extra: Any) -> None:
        self.status = status
        await bus.publish(
            "agent.status",
            agent=self.cfg.name,
            role=self.cfg.role,
            provider=self.cfg.provider.provider,
            model=self.cfg.provider.target,
            endpoint=self.cfg.provider.endpoint,
            status=status,
            queued=self.queued_enabled,
            search=self.search_enabled,
            fetch=self.fetch_enabled,
            **extra,
        )

    async def _on_enqueue(self, stats: QueueStats) -> None:
        # Only surface "queued" when the request actually has to wait.
        if stats.will_contend:
            self.queue_waiting = stats.waiting
            await self._set_status(
                "queued",
                queue_waiting=stats.waiting,
                queue_active=stats.active,
                queue_max=stats.max_concurrency,
            )

    async def _on_start(self, stats: QueueStats) -> None:
        self.queue_waiting = 0
        await self._set_status("thinking", queue_active=stats.active)

    async def _llm_call(self) -> str:
        """One provider round-trip, serialized through the queue if configured."""
        if self.queue is not None:
            return await self.queue.run(
                self._chat_with_retry,
                on_enqueue=self._on_enqueue,
                on_start=self._on_start,
            )
        await self._set_status("thinking")
        return await self._chat_with_retry()

    async def _chat_with_retry(self) -> str:
        """Call the provider, retrying transient failures (429/timeout/5xx) with backoff.

        Retrying INSIDE the queue slot is deliberate: while this agent waits out a rate
        limit, siblings sharing the backend don't pile more requests onto it. Non-retriable
        errors (auth, content filter, bad request) surface immediately.
        """
        delay = _RETRY_BASE_DELAY_S
        for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
            try:
                return await self.provider.chat(self.history)
            except ProviderError as exc:
                if not getattr(exc, "retriable", False) or attempt == MAX_LLM_ATTEMPTS:
                    raise
                wait = min(getattr(exc, "retry_after", None) or delay, _RETRY_MAX_DELAY_S)
                log.warning(
                    "agent %s: transient provider error (attempt %d/%d), retrying in %.0fs: %s",
                    self.cfg.name, attempt, MAX_LLM_ATTEMPTS, wait, exc,
                )
                await self._set_status(
                    "thinking", retrying=attempt, retry_in_s=round(wait, 1), error=str(exc)[:200]
                )
                await asyncio.sleep(wait)
                delay *= 2
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _last_line(reply: str) -> str:
        lines = reply.rstrip().splitlines()
        return lines[-1] if lines else ""

    def _line_tools(self) -> list[tuple[str, "re.Pattern[str]", int, Any]]:
        """The single-line directives this agent holds: (label, regex, per-turn max, runner).

        Each runner takes the regex match and returns the feedback payload string. One table
        instead of five hand-rolled parse/budget/run blocks.
        """
        tools: list[tuple[str, re.Pattern[str], int, Any]] = []
        if self.search is not None:
            tools.append(("SEARCH", SEARCH_RE, MAX_SEARCHES_PER_TURN,
                          lambda m: self._run_search(m.group("query").strip())))
        if self.fetcher is not None:
            tools.append(("FETCH", FETCH_RE, MAX_FETCHES_PER_TURN,
                          lambda m: self._run_fetch(m.group("url").strip())))
        if self.browser is not None:
            tools.append(("BROWSE", BROWSE_RE, MAX_BROWSES_PER_TURN,
                          lambda m: self._run_browse(m.group("url").strip())))
        if self.calc:
            tools.append(("CALC", CALC_RE, MAX_CALCS_PER_TURN,
                          lambda m: self._run_calc(m.group("expr").strip())))
        if self.mcp is not None:
            tools.append(("TOOL", MCP_RE, MAX_MCP_CALLS_PER_TURN,
                          lambda m: self._run_mcp(m.group("name"), m.group("args") or "")))
        return tools

    async def _run_turn(self) -> str:
        """Generate a reply, running the tool loop if this agent holds any tools.

        Each turn the model may end a reply with one tool directive — READ/EDIT/EXEC
        (spec 004) or a single-line directive (SEARCH/FETCH/BROWSE/CALC/TOOL) — which the
        runtime executes and feeds back as the next turn. A reply with no directive is the
        final answer.
        """
        line_tools = self._line_tools()
        used: dict[str, int] = {}
        for _ in range(MAX_TOOL_CALLS_PER_TURN):
            reply = await self._llm_call()

            call = parse_tool_call(reply) if self.executor is not None else None
            if call is not None:
                self.history.append({"role": "assistant", "content": reply})
                self.history.append({"role": "user", "content": await self._run_tool(call)})
                continue

            # Misformatted tool attempt (e.g. several READ: lines at once, or a directive
            # buried mid-reply): correct the model instead of taking it as a final answer.
            if self.executor is not None and has_directive_lines(reply):
                self.history.append({"role": "assistant", "content": reply})
                self.history.append(
                    {
                        "role": "user",
                        "content": (
                            "[runtime] Your reply contained tool directives the runtime could "
                            "not execute. Issue EXACTLY ONE directive per reply, as the LAST "
                            "line — tools run one at a time. Only EDIT: is followed by a "
                            "fenced block (the file's FULL new contents); READ:/EXEC: take "
                            "nothing after them. See the real result next turn, then decide "
                            "your next step. Resend just your FIRST step now."
                        ),
                    }
                )
                continue

            last = self._last_line(reply)
            matched = next(
                ((label, mx, run, m) for label, rx, mx, run in line_tools
                 if (m := rx.match(last)) is not None),
                None,
            )
            if matched is None:
                return reply

            label, mx, run, m = matched
            self.history.append({"role": "assistant", "content": reply})
            if used.get(label, 0) >= mx:
                self.history.append(
                    {
                        "role": "user",
                        "content": (
                            f"[runtime] {label} budget exhausted ({mx} per turn). Answer now "
                            f"using what you have; do NOT issue another {label} line."
                        ),
                    }
                )
                return await self._llm_call()
            used[label] = used.get(label, 0) + 1
            self.history.append({"role": "user", "content": await run(m)})

        # Total tool budget exhausted — force a final answer with no further tool use.
        self.history.append(
            {
                "role": "user",
                "content": (
                    "[runtime] Tool budget exhausted. Answer now using what you have; do NOT "
                    "issue another tool directive."
                ),
            }
        )
        return await self._llm_call()

    async def _run_search(self, query: str) -> str:
        """Run one web query and return the payload to feed back (emits tool.search events)."""
        assert self.search is not None
        await self._set_status("searching", query=query)
        await bus.publish("tool.search", agent=self.cfg.name, phase="query", query=query)
        try:
            results = await self.search.search(query, self.search_max_results)
            payload = format_results(query, results)
            await bus.publish(
                "tool.search",
                agent=self.cfg.name,
                phase="results",
                query=query,
                count=len(results),
                results=[r.as_dict() for r in results],
            )
        except SearchError as exc:
            payload = f"[search error] {exc}. Do not fabricate; tell the Planner the lookup failed."
            await bus.publish(
                "tool.search", agent=self.cfg.name, phase="error", query=query, error=str(exc)
            )
        return f"[search results]\n{payload}"

    async def _run_fetch(self, url: str) -> str:
        """Fetch one url and return the payload to feed back (emits tool.fetch events)."""
        assert self.fetcher is not None
        await self._set_status("fetching", url=url)
        await bus.publish("tool.fetch", agent=self.cfg.name, phase="request", url=url)
        try:
            result = await self.fetcher.fetch(url)
            payload = format_fetch_result(result)
            await bus.publish(
                "tool.fetch",
                agent=self.cfg.name,
                phase="result",
                **result.as_dict(),  # includes the requested url + finalUrl
            )
            self._prov_emit(
                "tool.fetch",
                url=url,
                finalUrl=result.final_url,
                statusCode=result.status_code,
                contentType=result.content_type,
                chars=len(result.text),
                truncated=result.truncated,
            )
        except FetchError as exc:
            payload = (
                f"[fetch error] {exc}. The page's contents are UNKNOWN to you — you did NOT "
                "see them. NEVER describe, quote, or summarize this url's content; if you "
                "mention the url at all, state that retrieval FAILED. Try a different url or "
                "report the failure to the Planner."
            )
            await bus.publish(
                "tool.fetch", agent=self.cfg.name, phase="error", url=url, error=str(exc)
            )
        return f"[fetched]\n{payload}"

    async def _run_browse(self, url: str) -> str:
        """Render one url in the headless browser (emits tool.fetch events, renderer-tagged)."""
        assert self.browser is not None
        await self._set_status("fetching", url=url)
        await bus.publish(
            "tool.fetch", agent=self.cfg.name, phase="request", url=url, renderer="browser"
        )
        try:
            result = await self.browser.fetch(url)
            payload = format_fetch_result(result)
            await bus.publish(
                "tool.fetch",
                agent=self.cfg.name,
                phase="result",
                renderer="browser",
                **result.as_dict(),
            )
            self._prov_emit(
                "tool.browse",
                url=url,
                finalUrl=result.final_url,
                statusCode=result.status_code,
                chars=len(result.text),
                truncated=result.truncated,
            )
        except FetchError as exc:
            payload = (
                f"[browse error] {exc}. The page's contents are UNKNOWN to you — you did NOT "
                "see them. NEVER describe, quote, or summarize this url's content; report the "
                "failure if no alternative source works."
            )
            await bus.publish(
                "tool.fetch",
                agent=self.cfg.name,
                phase="error",
                url=url,
                renderer="browser",
                error=str(exc),
            )
        return f"[browsed]\n{payload}"

    async def _run_calc(self, expr: str) -> str:
        """Evaluate one sandboxed expression (emits tool.calc events)."""
        await self._set_status("working", tool="calc")
        try:
            result = calc_evaluate(expr)
            await bus.publish(
                "tool.calc", agent=self.cfg.name, phase="result", expr=expr, result=result
            )
            self._prov_emit("tool.calc", expr=expr, result=result[:500])
            payload = f"{expr}\n= {result}"
        except CalcError as exc:
            await bus.publish(
                "tool.calc", agent=self.cfg.name, phase="error", expr=expr, error=str(exc)
            )
            payload = f"[calc error] {exc}"
        return f"[calc]\n{payload}"

    async def _run_mcp(self, name: str, raw_args: str) -> str:
        """Invoke one external MCP tool (emits tool.mcp events)."""
        assert self.mcp is not None
        await self._set_status("working", tool=f"mcp:{name}")
        await bus.publish("tool.mcp", agent=self.cfg.name, phase="call", tool=name)
        try:
            args = parse_tool_args(raw_args)
            result = await self.mcp.call(name, args)
            await bus.publish(
                "tool.mcp",
                agent=self.cfg.name,
                phase="result",
                tool=name,
                chars=len(result),
            )
            self._prov_emit("tool.mcp", tool=name, args=args, chars=len(result))
            payload = result
        except McpError as exc:
            await bus.publish(
                "tool.mcp", agent=self.cfg.name, phase="error", tool=name, error=str(exc)
            )
            payload = (
                f"[tool error] {exc}. Do not fabricate the tool's output; adjust the call "
                "or report the failure."
            )
        return f"[tool {name}]\n{payload}"

    async def _run_tool(self, call: ToolCall) -> str:
        """Run one file/shell tool call off the event loop and return the feedback payload.

        A gated (boundary-crossing, T3) result raises :class:`ApprovalPending` — the turn is
        PAUSED for the principal's decision, not answered. A T4 (irreversible) action is
        refused outright: per the approval-gate policy the runtime does not even request
        approval without a verified backup, and this runtime has none.
        """
        assert self.executor is not None
        await self._set_status("working", tool=call.kind)
        result = await asyncio.to_thread(self.executor.execute, call)
        await self._emit_tool_events(result)
        if result.gated:
            if result.tier == "T4":
                return (
                    f"[denied] `{result.command}` is an irreversible (T4) action; the runtime "
                    "refuses it outright — no verified backup/recovery exists, so approval "
                    "cannot even be requested. Do not retry it; continue without it or report "
                    "what you cannot complete."
                )
            raise ApprovalPending(call, result)
        return result.as_feedback()

    def _prov_emit(self, kind: str, **payload: Any) -> None:
        """Append one tool action to the run's provenance log (constitution V, T021).

        Compact by design: full patches/output live in the event store and the run's
        artifacts; the JSONL records that-and-what happened. Never breaks the tool loop.
        """
        if self.prov is None:
            return
        try:
            self.prov.emit(kind, actor=self.cfg.name, **payload)
        except Exception:  # noqa: BLE001 — observability must not fail the action
            log.debug("provenance emit failed for %s", self.cfg.name, exc_info=True)

    async def _emit_tool_events(self, r: ToolResult) -> None:
        """Publish tool.file / tool.exec bus events (mirroring tool.search) and land each
        action in the append-only provenance log (spec 004)."""
        agent = self.cfg.name
        if r.kind == "read" and r.status == "ok":
            await events.emit_tool_file(
                agent, "read", path=r.path, size=len((r.content or "").encode("utf-8"))
            )
            self._prov_emit("tool.file", phase="read", path=r.path)
        elif r.kind == "edit" and r.status == "ok":
            await events.emit_tool_file(agent, "write", path=r.path)
            await events.emit_tool_file(
                agent,
                "diff",
                files=[asdict(f) for f in r.files],
                patch=r.patch,
                truncated=r.truncated or None,
            )
            self._prov_emit(
                "tool.file",
                phase="write",
                path=r.path,
                summary=r.summary,
                files=[asdict(f) for f in r.files],
            )
        elif r.kind == "exec":
            await events.emit_tool_exec(agent, "command", r.command or "")
            if r.status != "gated":
                await events.emit_tool_exec(
                    agent,
                    "output",
                    r.command or "",
                    exit_code=r.exit_code,
                    stdout=r.stdout or None,
                    stderr=r.stderr or None,
                    duration_ms=r.duration_ms,
                    timed_out=r.timed_out or None,
                    truncated=r.truncated or None,
                )
                self._prov_emit(
                    "tool.exec",
                    command=r.command,
                    exitCode=r.exit_code,
                    durationMs=r.duration_ms,
                    timedOut=r.timed_out,
                    tier=r.tier,
                )

    async def chat(self, user_content: str) -> str:
        """Run one task turn. May raise :class:`ApprovalPending` — the turn is then paused
        (awaiting the principal's decision), not failed; continue it with ``resume_turn``."""
        return await self._turn_with(user_content)

    async def resume_turn(self, feedback: str) -> str:
        """Continue a turn paused by :class:`ApprovalPending`, feeding the decision's outcome
        (the executed command's real result, or ``[approval denied]``). May pause again."""
        return await self._turn_with(feedback)

    async def _turn_with(self, user_content: str) -> str:
        self.history.append({"role": "user", "content": user_content})
        try:
            reply = await self._run_turn()
        except ApprovalPending:
            # Paused, not failed: keep the task and the directive reply in history so the
            # decision's feedback resumes the turn exactly where the model stopped.
            self.queue_waiting = 0
            await self._set_status("blocked")
            raise
        except Exception as exc:
            # Roll back the user turn we appended; otherwise the next chat() call
            # resends a now-orphaned user message and may compound the failure.
            if self.history and self.history[-1].get("role") == "user":
                self.history.pop()
            self.queue_waiting = 0
            await self._set_status("error", error=str(exc))
            raise
        self.history.append({"role": "assistant", "content": reply})
        await self._set_status("idle")
        return reply

    async def health(self) -> dict[str, Any]:
        h = await self.provider.health()
        h["agent"] = self.cfg.name
        h["role"] = self.cfg.role
        h["queued"] = self.queued_enabled
        h["search"] = self.search_enabled
        h["fetch"] = self.fetch_enabled
        h["browse"] = self.browse_enabled
        h["calc"] = self.calc
        h["mcp"] = self.mcp_enabled
        h["tools"] = self.tools_enabled
        return h

    def reset(self) -> None:
        if self.history and self.history[0]["role"] == "system":
            self.history = [self.history[0]]
        else:
            self.history = []
