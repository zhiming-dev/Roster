"""Tests for the BROWSE and TOOL (MCP) directives.

BROWSE is exercised through the agent loop with a fake browser (Chromium itself is not a
unit-test dependency) plus the graceful-degradation path. MCP gets a REAL integration
test: McpToolHost against the FastMCP stdio server in ``mcp_test_server.py``.
"""

import sys
import types
from pathlib import Path

import pytest

from roster.agent import Agent
from roster.fetch import FetchError, FetchResult
from roster.mcptool import McpError, McpServerSpec, McpToolHost, parse_tool_args


class _ScriptedProvider:
    def __init__(self, replies):
        self._replies = list(replies)
        self.provider = "fake"
        self.target = "fake-model"
        self.endpoint = "local"
        self.seen: list[list[str]] = []

    async def chat(self, history):
        self.seen.append([m["content"] for m in history])
        return self._replies.pop(0) if self._replies else "done."

    async def health(self):
        return {"ok": True}


def _agent(replies, **kwargs):
    cfg = types.SimpleNamespace(
        name="researcher",
        role="researcher",
        provider=types.SimpleNamespace(provider="fake", target="fake-model", endpoint="local"),
    )
    provider = _ScriptedProvider(replies)
    return (
        Agent(cfg=cfg, provider=provider, history=[{"role": "system", "content": "sys"}], **kwargs),
        provider,
    )


# ---- BROWSE ----------------------------------------------------------------------


class _FakeBrowser:
    def __init__(self, fail=False):
        self._fail = fail
        self.browsed: list[str] = []

    async def fetch(self, url):
        self.browsed.append(url)
        if self._fail:
            raise FetchError("BROWSE unavailable: playwright is not installed — install it")
        return FetchResult(
            url=url, final_url=url, status_code=200,
            content_type="text/html (rendered)", text="RENDERED SPA CONTENT",
        )

    async def aclose(self):
        pass


async def test_browse_directive_feeds_rendered_text_back():
    browser = _FakeBrowser()
    agent, provider = _agent(
        ["FETCH came back empty; rendering.\nBROWSE: https://spa.example.com/quotes",
         "Got the rendered value."],
        browser=browser,
    )
    reply = await agent.chat("read the SPA page")
    assert reply == "Got the rendered value."
    assert browser.browsed == ["https://spa.example.com/quotes"]
    assert any("[browsed]" in m and "RENDERED SPA CONTENT" in m for m in provider.seen[1])


async def test_browse_unavailable_degrades_to_feedback():
    agent, provider = _agent(
        ["BROWSE: https://spa.example.com", "Cannot render; reporting the failure."],
        browser=_FakeBrowser(fail=True),
    )
    reply = await agent.chat("render it")
    assert reply == "Cannot render; reporting the failure."
    assert any("[browse error]" in m and "playwright" in m for m in provider.seen[1])


# ---- TOOL (MCP) -------------------------------------------------------------------


def test_parse_tool_args():
    assert parse_tool_args("") == {}
    assert parse_tool_args('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}
    with pytest.raises(McpError, match="JSON"):
        parse_tool_args("{a: 1}")
    with pytest.raises(McpError, match="object"):
        parse_tool_args("[1, 2]")


@pytest.fixture
async def mcp_host():
    server = Path(__file__).parent / "mcp_test_server.py"
    host = McpToolHost(
        [McpServerSpec(name="test", command=sys.executable, args=[str(server)])]
    )
    await host.start()
    yield host
    await host.aclose()


async def test_mcp_host_lists_and_calls_real_server(mcp_host):
    assert not mcp_host.errors
    assert {"add", "shout"} <= set(mcp_host.tools)
    assert "Add two integers" in mcp_host.tools["add"].description
    assert await mcp_host.call("add", {"a": 19, "b": 23}) == "42"
    assert await mcp_host.call("shout", {"text": "quiet"}) == "QUIET"


async def test_mcp_host_unknown_tool_names_catalog(mcp_host):
    with pytest.raises(McpError, match="add"):
        await mcp_host.call("no_such_tool", {})


async def test_mcp_catalog_prompt_lists_tools(mcp_host):
    catalog = mcp_host.catalog_prompt()
    assert "`add`" in catalog and "a*:integer" in catalog
    assert "TOOL:" in catalog


async def test_mcp_dead_server_is_skipped_not_fatal():
    host = McpToolHost(
        [McpServerSpec(name="dead", command=sys.executable, args=["-c", "raise SystemExit(1)"])]
    )
    await host.start()
    assert host.started
    assert host.tools == {}
    assert "dead" in host.errors
    await host.aclose()


async def test_tool_directive_through_agent_loop(mcp_host):
    agent, provider = _agent(
        ['Adding.\nTOOL: add {"a": 2, "b": 3}', "The sum is 5."],
        mcp=mcp_host,
    )
    reply = await agent.chat("add 2 and 3 with the external tool")
    assert reply == "The sum is 5."
    assert any("[tool add]" in m and m.rstrip().endswith("5") for m in provider.seen[1])


async def test_tool_directive_bad_json_feeds_corrective(mcp_host):
    agent, provider = _agent(
        ["TOOL: add {a: 2}", "Let me report the arg problem."],
        mcp=mcp_host,
    )
    reply = await agent.chat("add")
    assert reply == "Let me report the arg problem."
    assert any("[tool error]" in m and "JSON" in m for m in provider.seen[1])
