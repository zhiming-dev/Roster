"""JS-rendered page fetch — the `BROWSE:` directive's backend.

FETCH downloads a url's raw response, which is empty scaffolding for JS-rendered sites
(SPAs, many market-data pages). BROWSE loads the page in headless Chromium via Playwright,
lets scripts run, and returns the *rendered* text. It is the heavyweight fallback: agents
are told to FETCH first and BROWSE only when the fetched page came back as a JS shell.

Playwright is an optional dependency: when it (or its browser) is missing, every call
returns an honest, actionable :class:`~roster.fetch.FetchError` instead of crashing —
mirroring how the workspace tools degrade when no target repo is configured.
"""

from __future__ import annotations

import logging
from typing import Any

from .fetch import DEFAULT_MAX_CHARS, FetchError, FetchResult, check_url

log = logging.getLogger("roster.browse")

_INSTALL_HINT = (
    "run `pip install playwright && playwright install chromium` in the runtime venv"
)


class BrowserFetcher:
    """Render one url in headless Chromium and return its visible text.

    One shared instance per run; the browser launches lazily on first use and is reused
    across calls (launching Chromium per-fetch would dominate the latency).
    """

    name = "playwright-chromium"

    def __init__(self, timeout_s: float = 30.0, max_chars: int = DEFAULT_MAX_CHARS) -> None:
        self.timeout_ms = int(timeout_s * 1000)
        self.max_chars = max_chars
        self._pw: Any | None = None
        self._browser: Any | None = None

    async def _ensure_browser(self) -> Any:
        if self._browser is not None and self._browser.is_connected():
            return self._browser
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise FetchError(f"BROWSE unavailable: playwright is not installed — {_INSTALL_HINT}") from exc
        try:
            if self._pw is None:
                self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 — missing browser binary, sandbox issues
            raise FetchError(
                f"BROWSE unavailable: Chromium failed to launch ({exc}) — {_INSTALL_HINT}"
            ) from exc
        return self._browser

    async def fetch(self, url: str) -> FetchResult:
        cleaned = check_url(url)
        browser = await self._ensure_browser()
        context = await browser.new_context()
        try:
            page = await context.new_page()
            try:
                response = await page.goto(
                    cleaned, wait_until="domcontentloaded", timeout=self.timeout_ms
                )
            except Exception as exc:  # noqa: BLE001 — nav timeout, DNS, TLS…
                raise FetchError(f"BROWSE failed for {cleaned}: {exc}") from exc
            # Give scripts a moment to settle; a busy page never reaches networkidle,
            # so treat the extra wait as best-effort rather than a requirement.
            try:
                await page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:  # noqa: BLE001
                pass
            title = await page.title()
            body = await page.evaluate("document.body ? document.body.innerText : ''")
        finally:
            await context.close()

        text = (f"{title}\n\n" if title else "") + (body or "").strip()
        truncated = len(text) > self.max_chars
        if truncated:
            text = text[: self.max_chars]
        return FetchResult(
            url=cleaned,
            final_url=page.url,
            status_code=response.status if response else 0,
            content_type="text/html (rendered)",
            text=text,
            truncated=truncated,
        )

    async def aclose(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
            if self._pw is not None:
                await self._pw.stop()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            log.debug("browser close failed", exc_info=True)
        self._browser = None
        self._pw = None
