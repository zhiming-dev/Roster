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
from .store import Store, db_path

log = logging.getLogger("roster.server")

STATIC_DIR = Path(__file__).parent.parent / "static"
# The React SPA (spec 002) builds here; absent on a fresh clone, where we fall
# back to the committed single-file dashboard so the UI still works.
SPA_DIR = STATIC_DIR / "app"

_run: Run | None = None
_run_lock = asyncio.Lock()
_store: Store | None = None
_persist_task: asyncio.Task[None] | None = None


def _get_config_path() -> str:
    return os.environ.get("ROSTER_CONFIG") or os.environ.get("CONCLAVE_CONFIG", "agents.config.yaml")


def _get_store() -> Store:
    global _store
    if _store is None:
        _store = Store(db_path())
    return _store


async def _announce(run: Run) -> None:
    """Publish the agent roster + run banner so a (re)connecting dashboard and the
    persistence layer observe a consistent starting state for this run."""
    for a in run.all_agents():
        await bus.publish(
            "agent.status",
            agent=a.cfg.name,
            role=a.cfg.role,
            provider=a.cfg.provider.provider,
            model=a.cfg.provider.target,
            endpoint=a.cfg.provider.endpoint,
            status=a.status,
            queued=a.queued_enabled,
            search=a.search_enabled,
        )
    await bus.publish("run.started", runId=run.run_id, queue=run.queue_stats())


async def _ensure_run() -> Run:
    global _run
    async with _run_lock:
        if _run is None:
            _run = Run(_get_config_path())
            await _get_store().ensure_conversation(_run.run_id)
            await _announce(_run)
        return _run


async def _persist_events() -> None:
    """Background consumer: append every bus event to the active conversation."""
    q = bus.subscribe()
    try:
        while True:
            evt = await q.get()
            run = _run
            if run is None:
                continue
            try:
                await _get_store().add_event(run.run_id, evt)
            except Exception:  # noqa: BLE001 - persistence must never break the feed
                log.debug("event persistence failed", exc_info=True)
    except asyncio.CancelledError:
        raise
    finally:
        bus.unsubscribe(q)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _run, _store, _persist_task
    _get_store()
    _persist_task = asyncio.create_task(_persist_events())
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
        if _persist_task is not None:
            _persist_task.cancel()
            try:
                await _persist_task
            except asyncio.CancelledError:
                pass
        if _run is not None:
            await _run.aclose()
        if _store is not None:
            await _store.aclose()


app = FastAPI(title="Roster Runtime", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve the built SPA's hashed assets under /app (its `base`). Mounted only when
# a build is present; otherwise the legacy dashboard is served at / instead.
if SPA_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=str(SPA_DIR)), name="app")


@app.get("/")
async def index() -> FileResponse:
    spa_index = SPA_DIR / "index.html"
    if spa_index.is_file():
        return FileResponse(str(spa_index))
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
        result = await run.handle_principal_message(text)
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
    # When the planner pauses to ask the principal, the run stays live (awaiting_input)
    # and the next /api/chat message is routed as the answer (resumed in the orchestrator).
    if result.status == "awaiting_input":
        return JSONResponse(
            {"status": "awaiting_input", "question": result.text, "runId": run.run_id}
        )
    return JSONResponse({"status": "done", "reply": result.text, "runId": run.run_id})


@app.post("/api/reset")
async def reset() -> JSONResponse:
    global _run
    async with _run_lock:
        old, _run = _run, None
    if old is not None:
        await old.aclose()
    run = await _ensure_run()
    return JSONResponse({"runId": run.run_id})


@app.get("/api/conversations")
async def list_conversations() -> JSONResponse:
    convos = await _get_store().list_conversations()
    return JSONResponse(
        {"conversations": convos, "active": _run.run_id if _run is not None else None}
    )


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str) -> JSONResponse:
    store = _get_store()
    if not await store.exists(conv_id):
        return JSONResponse({"error": "not found"}, status_code=404)
    events = await store.get_events(conv_id)
    return JSONResponse(
        {
            "id": conv_id,
            "events": events,
            "active": _run.run_id if _run is not None else None,
        }
    )


@app.post("/api/conversations/{conv_id}/activate")
async def activate_conversation(conv_id: str) -> JSONResponse:
    """Reopen a persisted conversation: rebind it as the live run (restoring the
    planner's history) and return its events so the dashboard can replay them."""
    global _run
    store = _get_store()
    if not await store.exists(conv_id):
        return JSONResponse({"error": "not found"}, status_code=404)
    events = await store.get_events(conv_id)
    async with _run_lock:
        if _run is not None and _run.run_id == conv_id:
            run = _run
        else:
            old, _run = _run, None
            run = Run(_get_config_path(), run_id=conv_id)
            run.resume_from_events(events)
            _run = run
            if old is not None:
                await old.aclose()
    await _announce(run)
    return JSONResponse({"id": conv_id, "events": events})


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str) -> JSONResponse:
    """Delete a conversation. If it was the live run, start a fresh one."""
    global _run
    store = _get_store()
    async with _run_lock:
        active = _run is not None and _run.run_id == conv_id
        if active:
            old, _run = _run, None
            await old.aclose()
    await store.delete_conversation(conv_id)
    if active:
        await _ensure_run()
    return JSONResponse({"ok": True, "active": _run.run_id if _run is not None else None})


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await socket.accept()
    q = bus.subscribe()
    try:
        # Live-only stream. Initial/historical state is loaded by the dashboard
        # per-conversation from the SQLite store (GET /api/conversations/{id}),
        # so replaying the global in-memory bus history here would bleed events
        # from other runs into the open conversation.
        while True:
            evt = await q.get()
            await socket.send_text(json.dumps(evt, ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)
