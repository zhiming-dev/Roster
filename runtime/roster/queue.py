"""Shared, observable LLM request queue.

When several agents share a single backend / API key, concurrent calls cause rate-limit
errors (cloud) or memory thrash (local). The queue serializes those agents: an agent
listed in `queue.require_queue` submits its call through :meth:`LlmQueue.run`, which admits
at most `max_concurrency` calls at once (1 by default) and makes the rest wait in FIFO
order. Agents not in the list bypass the queue entirely.

The queue is intentionally backend-agnostic and bus-agnostic: callers pass `on_enqueue` /
`on_start` callbacks so the waiting/active transitions can be surfaced as status events
without coupling the queue to the dashboard.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

StateCallback = Callable[["QueueStats"], Awaitable[None]]


@dataclass(frozen=True)
class QueueStats:
    waiting: int
    active: int
    max_concurrency: int

    @property
    def will_contend(self) -> bool:
        """True if a request entering now would have to wait for a slot."""
        return self.active >= self.max_concurrency


class LlmQueue:
    def __init__(self, max_concurrency: int = 1) -> None:
        self.max_concurrency = max(1, int(max_concurrency))
        self._sem = asyncio.Semaphore(self.max_concurrency)
        self._waiting = 0
        self._active = 0

    def stats(self) -> QueueStats:
        return QueueStats(self._waiting, self._active, self.max_concurrency)

    async def run(
        self,
        fn: Callable[[], Awaitable[T]],
        *,
        on_enqueue: StateCallback | None = None,
        on_start: StateCallback | None = None,
    ) -> T:
        """Run `fn` under the queue's concurrency limit.

        `on_enqueue` fires once the request is counted as waiting (before it acquires a
        slot); `on_start` fires once it has a slot and is about to execute. Counters are
        kept consistent even if the awaiting task is cancelled while queued.
        """
        self._waiting += 1
        acquired = False
        try:
            if on_enqueue is not None:
                await on_enqueue(self.stats())
            await self._sem.acquire()
            acquired = True
            self._waiting -= 1
            self._active += 1
            if on_start is not None:
                await on_start(self.stats())
            return await fn()
        finally:
            if acquired:
                self._active -= 1
                self._sem.release()
            else:
                self._waiting -= 1
