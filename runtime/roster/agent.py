"""Live agent: an agent definition (.agent.md) bound to a provider, with chat history,
an observable status, optional routing through the shared LLM queue, and an optional
web-search tool loop.

Status lifecycle: ``idle`` → (``queued`` →) ``thinking`` → (``searching`` | ``working`` →
``thinking`` …) → ``idle`` | ``error``. ``queued`` appears only for agents in
``queue.require_queue`` when the queue is contended; ``searching`` appears while a web query is
in flight; ``working`` appears while a file/shell tool (spec 004) runs.
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
from .protocol import ToolCall, parse_tool_call
from .providers import Provider, build_provider
from .queue import LlmQueue, QueueStats
from .search import SearchError, SearchProvider, format_results
from .tools import ToolExecutor, ToolResult

log = logging.getLogger("roster.agent")

# A tool call the model emits as the LAST line of a reply, mirroring DISPATCH:.
SEARCH_RE = re.compile(r"^\s*SEARCH\s*:\s*(?P<query>.+?)\s*$", re.IGNORECASE)

MAX_SEARCHES_PER_TURN = 3
# Total tool directives (read/edit/exec + search) the runtime runs in one turn before forcing a
# final answer. Generous for a coder (read a few files, edit, run tests, fix), but bounded.
MAX_TOOL_CALLS_PER_TURN = 16


@dataclass
class Agent:
    cfg: AgentConfig
    provider: Provider
    queue: LlmQueue | None = None  # set when this agent must serialize through the queue
    search: SearchProvider | None = None  # set when this agent has the `search` tool
    executor: ToolExecutor | None = None  # set when this agent has file/shell tools (spec 004)
    search_max_results: int = 5
    history: list[dict[str, str]] = field(default_factory=list)
    status: str = "idle"  # idle | queued | thinking | searching | working | error
    queue_waiting: int = 0

    @classmethod
    def from_config(
        cls,
        cfg: AgentConfig,
        runtime_suffix: str = "",
        queue: LlmQueue | None = None,
        search: SearchProvider | None = None,
        search_max_results: int = 5,
        executor: ToolExecutor | None = None,
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
            executor=executor,
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
                lambda: self.provider.chat(self.history),
                on_enqueue=self._on_enqueue,
                on_start=self._on_start,
            )
        await self._set_status("thinking")
        return await self.provider.chat(self.history)

    @staticmethod
    def _parse_search(reply: str) -> str | None:
        lines = reply.rstrip().splitlines()
        if not lines:
            return None
        m = SEARCH_RE.match(lines[-1])
        return m.group("query").strip() if m else None

    async def _run_turn(self) -> str:
        """Generate a reply, running the tool loop (file/shell tools + web search) if present.

        Each turn the model may end a reply with one tool directive — READ/EDIT/EXEC (spec 004)
        or SEARCH — which the runtime executes and feeds back as the next turn, exactly like the
        original search loop. A reply with no directive is the final answer.
        """
        searches = 0
        for _ in range(MAX_TOOL_CALLS_PER_TURN):
            reply = await self._llm_call()

            call = parse_tool_call(reply) if self.executor is not None else None
            if call is not None:
                self.history.append({"role": "assistant", "content": reply})
                self.history.append({"role": "user", "content": await self._run_tool(call)})
                continue

            query = self._parse_search(reply) if self.search is not None else None
            if query is not None:
                self.history.append({"role": "assistant", "content": reply})
                if searches >= MAX_SEARCHES_PER_TURN:
                    self.history.append(
                        {
                            "role": "user",
                            "content": (
                                "[runtime] Search budget exhausted. Answer now using what you "
                                "have; do NOT issue another SEARCH line."
                            ),
                        }
                    )
                    return await self._llm_call()
                searches += 1
                self.history.append({"role": "user", "content": await self._run_search(query)})
                continue

            return reply

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

    async def _run_tool(self, call: ToolCall) -> str:
        """Run one file/shell tool call off the event loop and return the feedback payload."""
        assert self.executor is not None
        await self._set_status("working", tool=call.kind)
        result = await asyncio.to_thread(self.executor.execute, call)
        await self._emit_tool_events(result)
        return result.as_feedback()

    async def _emit_tool_events(self, r: ToolResult) -> None:
        """Publish tool.file / tool.exec bus events, mirroring tool.search (spec 004)."""
        agent = self.cfg.name
        if r.kind == "read" and r.status == "ok":
            await events.emit_tool_file(
                agent, "read", path=r.path, size=len((r.content or "").encode("utf-8"))
            )
        elif r.kind == "edit" and r.status == "ok":
            await events.emit_tool_file(agent, "write", path=r.path)
            await events.emit_tool_file(
                agent,
                "diff",
                files=[asdict(f) for f in r.files],
                patch=r.patch,
                truncated=r.truncated or None,
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

    async def chat(self, user_content: str) -> str:
        self.history.append({"role": "user", "content": user_content})
        try:
            reply = await self._run_turn()
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
        h["tools"] = self.tools_enabled
        return h

    def reset(self) -> None:
        if self.history and self.history[0]["role"] == "system":
            self.history = [self.history[0]]
        else:
            self.history = []
