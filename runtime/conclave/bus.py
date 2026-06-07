"""In-process pub/sub for dashboard live events. Async-only."""

from __future__ import annotations

import asyncio
import time
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[dict[str, Any]]] = set()
        self._history: list[dict[str, Any]] = []
        self._history_cap = 500

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subs.discard(q)

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    async def publish(self, kind: str, **payload: Any) -> None:
        evt = {"kind": kind, "ts": time.time(), **payload}
        self._history.append(evt)
        if len(self._history) > self._history_cap:
            self._history = self._history[-self._history_cap :]
        dead: list[asyncio.Queue[dict[str, Any]]] = []
        for q in self._subs:
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subs.discard(q)


bus = EventBus()
