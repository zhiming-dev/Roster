"""A minimal MCP server used by the McpToolHost integration tests (stdio transport).

Run directly: ``python mcp_test_server.py``. Exposes two trivial tools so the tests can
verify the whole list-tools → call-tool → text-content path against a REAL server.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("roster-test")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@mcp.tool()
def shout(text: str) -> str:
    """Return the text uppercased."""
    return text.upper()


if __name__ == "__main__":
    mcp.run()
