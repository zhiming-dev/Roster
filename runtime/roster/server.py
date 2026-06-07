"""FastAPI server: principal chat + WebSocket dashboard feed."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .bus import bus
from .orchestrator import Run
from .providers import ProviderError

log = logging.getLogger("roster.server")

STATIC_DIR = Path(__file__).parent.parent / "static"

_run: Run | None = None
_run_lock = asyncio.Lock()


def _get_config_path() -> str:
    return os.environ.get("ROSTER_CONFIG") or os.environ.get("CONCLAVE_CONFIG", "agents.config.yaml")


async def _ensure_run() -> Run:
    global _run
    async with _run_lock:
        if _run is None:
            _run = Run(_get_config_path())
            for a in _run.all_agents():
                await bus.publish(
                    "agent.status",
                    agent=a.cfg.name,
                    role=a.cfg.role,
                    provider=a.cfg.provider.provider,
                    model=a.cfg.provider.target,
                    endpoint=a.cfg.provider.endpoint,
                    status=a.status,
                    queued=a.queued_enabled,
                )
            await bus.publish(
                "run.started", runId=_run.run_id, queue=_run.queue_stats()
            )
        return _run


@asynccontextmanager
async def lifespan(app: FastAPI):
    run = await _ensure_run()
    # Eager health check on startup so missing models / unreachable providers
    # show up in the terminal before the first chat triggers a long stall.
    for h in await run.health():
        if not h.get("ok"):
            log.warning(
                "agent=%s provider=%s unreachable: %s — %s",
                h.get("agent"),
                h.get("provider"),
                h.get("error"),
                h.get("hint"),
            )
        elif not h.get("model_present", True):
            log.warning("agent=%s model not pulled: %s", h.get("agent"), h.get("hint"))
    try:
        yield
    finally:
        global _run
        if _run is not None:
            await _run.aclose()


app = FastAPI(title="Roster Runtime", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "dashboard.html"))


@app.get("/api/health")
async def health() -> JSONResponse:
    run = await _ensure_run()
    return JSONResponse(
        {
            "runId": run.run_id,
            "queue": run.queue_stats(),
            "agents": await run.health(),
        }
    )


@app.get("/api/queue")
async def queue() -> JSONResponse:
    run = await _ensure_run()
    return JSONResponse({"runId": run.run_id, "queue": run.queue_stats()})


@app.get("/api/agents")
async def agents() -> JSONResponse:
    run = await _ensure_run()
    return JSONResponse(
        {
            "runId": run.run_id,
            "queue": run.queue_stats(),
            "agents": [
                {
                    "name": a.cfg.name,
                    "role": a.cfg.role,
                    "status": a.status,
                    "queued": a.queued_enabled,
                    "queue_waiting": a.queue_waiting,
                    "search": a.search_enabled,
                    "tools": a.cfg.tools,
                    "description": a.cfg.description,
                    "system_prompt_chars": len(a.history[0]["content"])
                    if a.history and a.history[0].get("role") == "system"
                    else 0,
                    # Secret-safe: api_key is never serialized.
                    **a.cfg.provider.public_dict(),
                }
                for a in run.all_agents()
            ],
        }
    )


@app.post("/api/chat")
async def chat(payload: dict[str, Any]) -> JSONResponse:
    text = (payload.get("message") or "").strip()
    if not text:
        return JSONResponse({"error": "empty message"}, status_code=400)
    run = await _ensure_run()
    try:
        reply = await run.handle_principal_message(text)
    except ProviderError as exc:
        await bus.publish("runtime.error", scope="chat", error=str(exc))
        return JSONResponse(
            {"error": str(exc), "kind": "provider_error", "runId": run.run_id},
            status_code=502,
        )
    except Exception as exc:
        log.exception("chat handler failed")
        await bus.publish("runtime.error", scope="chat", error=repr(exc))
        return JSONResponse(
            {
                "error": f"{type(exc).__name__}: {exc}",
                "kind": "internal_error",
                "runId": run.run_id,
            },
            status_code=500,
        )
    return JSONResponse({"reply": reply, "runId": run.run_id})


@app.post("/api/reset")
async def reset() -> JSONResponse:
    global _run
    async with _run_lock:
        old, _run = _run, None
    if old is not None:
        await old.aclose()
    run = await _ensure_run()
    return JSONResponse({"runId": run.run_id})


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await socket.accept()
    q = bus.subscribe()
    try:
        # Replay recent history so a late-joining dashboard isn't empty.
        for evt in bus.history():
            await socket.send_text(json.dumps(evt, ensure_ascii=False))
        while True:
            evt = await q.get()
            await socket.send_text(json.dumps(evt, ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)
