"""Live agent: an agent definition (.agent.md) bound to a provider, with chat history,
an observable status, optional routing through the shared LLM queue, and an optional
web-search tool loop.

Status lifecycle: ``idle`` → (``queued`` →) ``thinking`` → (``searching`` → ``thinking`` …)
→ ``idle`` | ``error``. The ``queued`` state appears only for agents in
``queue.require_queue`` when the queue is contended; ``searching`` appears only for agents
granted the ``search`` tool while a web query is in flight.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .bus import bus
from .config import AgentConfig
from .providers import Provider, build_provider
from .queue import LlmQueue, QueueStats
from .search import SearchError, SearchProvider, format_results

log = logging.getLogger("conclave.agent")

# A tool call the model emits as the LAST line of a reply, mirroring DISPATCH:.
SEARCH_RE = re.compile(r"^\s*SEARCH\s*:\s*(?P<query>.+?)\s*$", re.IGNORECASE)

MAX_SEARCHES_PER_TURN = 3


@dataclass
class Agent:
    cfg: AgentConfig
    provider: Provider
    queue: LlmQueue | None = None  # set when this agent must serialize through the queue
    search: SearchProvider | None = None  # set when this agent has the `search` tool
    search_max_results: int = 5
    history: list[dict[str, str]] = field(default_factory=list)
    status: str = "idle"  # idle | queued | thinking | searching | error
    queue_waiting: int = 0

    @classmethod
    def from_config(
        cls,
        cfg: AgentConfig,
        runtime_suffix: str = "",
        queue: LlmQueue | None = None,
        search: SearchProvider | None = None,
        search_max_results: int = 5,
    ) -> "Agent":
        system = cfg.system_prompt
        if runtime_suffix:
            system = system + "\n\n---\n\n" + runtime_suffix
        return cls(
            cfg=cfg,
            provider=build_provider(cfg.provider),
            queue=queue,
            search=search,
            search_max_results=search_max_results,
            history=[{"role": "system", "content": system}],
        )

    @property
    def queued_enabled(self) -> bool:
        return self.queue is not None

    @property
    def search_enabled(self) -> bool:
        return self.search is not None

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
        """Generate a reply, running the web-search tool loop if the agent has it."""
        for _ in range(MAX_SEARCHES_PER_TURN):
            reply = await self._llm_call()
            if self.search is None:
                return reply
            query = self._parse_search(reply)
            if not query:
                return reply

            # The model asked to search — record its tool-call turn, run the query
            # (outside the LLM queue), feed results back, and let it continue.
            self.history.append({"role": "assistant", "content": reply})
            await self._set_status("searching", query=query)
            await bus.publish(
                "tool.search", agent=self.cfg.name, phase="query", query=query
            )
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
                payload = (
                    f"[search error] {exc}. Do not fabricate; tell the Planner the "
                    "lookup failed."
                )
                await bus.publish(
                    "tool.search",
                    agent=self.cfg.name,
                    phase="error",
                    query=query,
                    error=str(exc),
                )
            self.history.append(
                {"role": "user", "content": f"[search results]\n{payload}"}
            )

        # Budget exhausted — force a final answer with no further tool use.
        self.history.append(
            {
                "role": "user",
                "content": (
                    "[runtime] Search budget exhausted. Answer now using what you have; "
                    "do NOT issue another SEARCH line."
                ),
            }
        )
        return await self._llm_call()

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
        return h

    def reset(self) -> None:
        if self.history and self.history[0]["role"] == "system":
            self.history = [self.history[0]]
        else:
            self.history = []
