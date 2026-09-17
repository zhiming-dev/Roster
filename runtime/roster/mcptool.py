"""MCP client — the `TOOL:` directive's backend.

One implementation, a whole ecosystem: operators declare Model Context Protocol servers
in ``agents.config.yaml`` (``mcp_servers:``), and every agent granted the ``mcp`` tool can
call any tool those servers expose, via:

    TOOL: <tool_name> {"arg": "value"}

The host connects to each server over stdio, merges their tool catalogs (collisions get a
``server.tool`` prefix), and injects a compact catalog into granted agents' system prompts
once connected. A server that fails to start is skipped with a logged warning — the run
degrades, it doesn't die.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("roster.mcp")

CALL_TIMEOUT_S = 60.0
_MAX_RESULT_CHARS = 8_000
_MAX_SCHEMA_CHARS = 400


class McpError(RuntimeError):
    """An MCP call failed in a way worth surfacing to the agent/operator."""


@dataclass
class McpServerSpec:
    """One server from the ``mcp_servers:`` config section."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None


@dataclass
class McpToolInfo:
    server: str
    name: str  # the name agents use (prefixed with "<server>." on collision)
    remote_name: str  # the name the server knows it by
    description: str
    schema: dict[str, Any] = field(default_factory=dict)


def _schema_summary(schema: dict[str, Any]) -> str:
    """Render an input schema compactly: ``name:type (required…)``."""
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    parts = []
    for pname, spec in props.items():
        ptype = spec.get("type", "any") if isinstance(spec, dict) else "any"
        star = "*" if pname in required else ""
        parts.append(f"{pname}{star}:{ptype}")
    out = ", ".join(parts) or "no arguments"
    return out[:_MAX_SCHEMA_CHARS]


class McpToolHost:
    """Owns the connections to every configured MCP server for one run."""

    def __init__(self, servers: list[McpServerSpec]) -> None:
        self._specs = servers
        self._stack = AsyncExitStack()
        self._sessions: dict[str, Any] = {}  # server name → ClientSession
        self.tools: dict[str, McpToolInfo] = {}  # agent-facing name → info
        self.errors: dict[str, str] = {}  # server name → why it was skipped
        self.started = False

    async def start(self) -> None:
        """Connect to every configured server and merge their tool catalogs."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        for spec in self._specs:
            try:
                params = StdioServerParameters(
                    command=spec.command,
                    args=list(spec.args),
                    env=spec.env,
                    cwd=spec.cwd,
                )
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(session.initialize(), timeout=30.0)
                listed = await asyncio.wait_for(session.list_tools(), timeout=30.0)
            except Exception as exc:  # noqa: BLE001 — a bad server must not kill the run
                self.errors[spec.name] = f"{type(exc).__name__}: {exc}"
                log.warning("mcp server '%s' failed to start: %s", spec.name, exc)
                continue
            self._sessions[spec.name] = session
            for t in listed.tools:
                public = t.name if t.name not in self.tools else f"{spec.name}.{t.name}"
                self.tools[public] = McpToolInfo(
                    server=spec.name,
                    name=public,
                    remote_name=t.name,
                    description=(t.description or "").strip(),
                    schema=dict(t.inputSchema or {}),
                )
            log.info("mcp server '%s': %d tools", spec.name, len(listed.tools))
        self.started = True

    def catalog_prompt(self) -> str:
        """The tool catalog block injected into granted agents' system prompts."""
        if not self.tools:
            return ""
        lines = ["## External tools available (via `TOOL:`)", ""]
        for info in self.tools.values():
            desc = info.description.splitlines()[0][:200] if info.description else ""
            lines.append(f"- `{info.name}` ({_schema_summary(info.schema)}) — {desc}")
        lines.append("")
        lines.append(
            'Call one by ending a reply with: TOOL: <name> {"arg": value, ...} '
            "(JSON args on the same line; omit the JSON when a tool takes no arguments)."
        )
        return "\n".join(lines)

    async def call(self, tool_name: str, args: dict[str, Any]) -> str:
        """Invoke one tool and return its text content (or a raised :class:`McpError`)."""
        info = self.tools.get(tool_name)
        if info is None:
            known = ", ".join(sorted(self.tools)) or "<none>"
            raise McpError(f"unknown tool '{tool_name}'. Available tools: {known}")
        session = self._sessions[info.server]
        try:
            result = await asyncio.wait_for(
                session.call_tool(info.remote_name, arguments=args or None),
                timeout=CALL_TIMEOUT_S,
            )
        except McpError:
            raise
        except asyncio.TimeoutError as exc:
            raise McpError(f"tool '{tool_name}' timed out after {CALL_TIMEOUT_S:.0f}s") from exc
        except Exception as exc:  # noqa: BLE001
            raise McpError(f"tool '{tool_name}' failed: {exc}") from exc

        parts: list[str] = []
        for block in result.content or []:
            if getattr(block, "type", "") == "text":
                parts.append(block.text)
            else:
                parts.append(f"[{getattr(block, 'type', 'non-text')} content]")
        text = "\n".join(parts).strip() or "(the tool returned no content)"
        if len(text) > _MAX_RESULT_CHARS:
            text = text[:_MAX_RESULT_CHARS] + "\n[result truncated]"
        if getattr(result, "isError", False):
            raise McpError(f"tool '{tool_name}' returned an error: {text[:1000]}")
        return text

    async def aclose(self) -> None:
        try:
            await self._stack.aclose()
        except Exception:  # noqa: BLE001 — anyio cancel-scope quirks on cross-task close
            log.debug("mcp stack close failed", exc_info=True)
        self._sessions.clear()


def parse_tool_args(raw: str) -> dict[str, Any]:
    """Parse the JSON argument blob of a TOOL: line (empty → {})."""
    raw = raw.strip()
    if not raw:
        return {}
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise McpError(
            f"arguments are not valid JSON ({exc.msg}). "
            'Write them as a single-line JSON object, e.g. TOOL: add {"a": 1, "b": 2}'
        ) from exc
    if not isinstance(args, dict):
        raise McpError("arguments must be a JSON object, e.g. {\"a\": 1}")
    return args
