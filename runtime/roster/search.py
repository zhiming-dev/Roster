"""Web search providers — the runtime's only real "tool" so far.

Zero-friction by design: with no configuration at all you get DuckDuckGo (no API
key). If a `TAVILY_API_KEY` is present (or `search.provider: tavily`), the cleaner
Tavily API is used instead. Both implement the same :class:`SearchProvider` shape so
more backends (Bing, Brave, Azure grounding) can drop in later.
"""

from __future__ import annotations

import html
import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .config import SearchConfig

log = logging.getLogger("roster.search")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def as_dict(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


class SearchError(RuntimeError):
    """A search backend failed in a way worth surfacing to the agent/operator."""


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...

    async def aclose(self) -> None: ...


def format_results(query: str, results: list[SearchResult]) -> str:
    """Render results compactly for feeding back into an LLM turn."""
    if not results:
        return (
            f"No web results were returned for '{query}'. Do not invent data; tell the "
            "Planner you could not retrieve it and suggest the user try again or provide "
            "a source."
        )
    lines = [f"Web results for '{query}':"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] {r.title}\n{r.url}\n{r.snippet}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# DuckDuckGo (no API key) — uses the lightweight HTML endpoint and tolerant parsing.
# --------------------------------------------------------------------------------------
class DuckDuckGoSearch:
    name = "duckduckgo"
    _ENDPOINT = "https://html.duckduckgo.com/html/"

    def __init__(self, timeout_s: float = 15.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            r = await self._client.post(self._ENDPOINT, data={"q": query})
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchError(f"DuckDuckGo request failed: {exc}") from exc
        return _parse_ddg_html(r.text, max_results)


def _strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _decode_ddg_url(href: str) -> str:
    # DDG often wraps targets as /l/?uddg=<urlencoded>&...
    if "uddg=" in href:
        q = urllib.parse.urlparse(href).query
        params = urllib.parse.parse_qs(q)
        if "uddg" in params:
            return params["uddg"][0]
    if href.startswith("//"):
        return "https:" + href
    return href


_DDG_LINK_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S
)
_DDG_SNIPPET_RE = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.S
)


def _parse_ddg_html(html_text: str, max_results: int) -> list[SearchResult]:
    links = _DDG_LINK_RE.findall(html_text)
    snippets = _DDG_SNIPPET_RE.findall(html_text)
    results: list[SearchResult] = []
    for i, (href, title) in enumerate(links[:max_results]):
        snippet = _strip_tags(snippets[i]) if i < len(snippets) else ""
        results.append(
            SearchResult(
                title=_strip_tags(title) or "(untitled)",
                url=_decode_ddg_url(href),
                snippet=snippet[:400],
            )
        )
    return results


# --------------------------------------------------------------------------------------
# Tavily (API key) — JSON API purpose-built for LLM grounding.
# --------------------------------------------------------------------------------------
class TavilySearch:
    name = "tavily"
    _ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: str, timeout_s: float = 20.0) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        payload: dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
            "search_depth": "basic",
        }
        try:
            r = await self._client.post(self._ENDPOINT, json=payload)
        except httpx.HTTPError as exc:
            raise SearchError(f"Tavily request failed: {exc}") from exc
        if r.status_code in (401, 403):
            raise SearchError("Tavily auth failed — check TAVILY_API_KEY.")
        if r.status_code >= 400:
            raise SearchError(f"Tavily returned {r.status_code}: {r.text[:200]}")
        data = r.json()
        out: list[SearchResult] = []
        for item in data.get("results", [])[:max_results]:
            out.append(
                SearchResult(
                    title=item.get("title", "(untitled)"),
                    url=item.get("url", ""),
                    snippet=(item.get("content", "") or "")[:400],
                )
            )
        return out


def build_search_provider(cfg: SearchConfig) -> SearchProvider | None:
    if not cfg.enabled:
        return None
    provider = (cfg.provider or "auto").lower()
    if provider in ("none", "off", "disabled"):
        return None
    if provider == "tavily" or (provider == "auto" and cfg.api_key):
        if not cfg.api_key:
            log.warning("search.provider=tavily but no api_key/TAVILY_API_KEY set; "
                        "falling back to DuckDuckGo")
            return DuckDuckGoSearch()
        return TavilySearch(cfg.api_key)
    # auto without a key, or explicitly duckduckgo
    return DuckDuckGoSearch()
