"""Ollama provider — local (or remote) Ollama daemon via /api/chat."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import ProviderConfig
from .base import Provider, ProviderError, merged_options

log = logging.getLogger("conclave.providers.ollama")


class OllamaProvider:
    """Talks to an Ollama daemon's /api/chat endpoint."""

    def __init__(self, cfg: ProviderConfig) -> None:
        self.cfg = cfg
        self._client = httpx.AsyncClient(
            base_url=cfg.endpoint,
            timeout=httpx.Timeout(cfg.request_timeout_s, connect=5.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        try:
            r = await self._client.get("/api/tags", timeout=5.0)
            r.raise_for_status()
            tags = r.json().get("models", [])
            present = any(
                m.get("name", "").split(":", 1)[0] == self.cfg.model.split(":", 1)[0]
                for m in tags
            )
            return {
                "ok": True,
                "provider": "ollama",
                "endpoint": self.cfg.endpoint,
                "model": self.cfg.model,
                "model_present": present,
                "hint": None if present else f"Run `ollama pull {self.cfg.model}`",
            }
        except Exception as exc:  # noqa: BLE001 - health must never raise
            return {
                "ok": False,
                "provider": "ollama",
                "endpoint": self.cfg.endpoint,
                "model": self.cfg.model,
                "error": str(exc),
                "hint": "Is `ollama serve` running?",
            }

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "stream": False,
            "options": merged_options(self.cfg, kwargs),
        }
        if self.cfg.keep_alive is not None:
            payload["keep_alive"] = self.cfg.keep_alive

        try:
            r = await self._client.post("/api/chat", json=payload)
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Cannot reach Ollama at {self.cfg.endpoint}. Is `ollama serve` running? ({exc})"
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ProviderError(
                f"Ollama timed out after {self.cfg.request_timeout_s:.0f}s. "
                "The model may be paging to disk; try a smaller model."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"HTTP error talking to Ollama: {exc}") from exc

        if r.status_code == 404:
            raise ProviderError(
                f"Ollama returned 404 for model '{self.cfg.model}'. "
                f"Pull it first: `ollama pull {self.cfg.model}`"
            )
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", r.text)
            except Exception:  # noqa: BLE001
                msg = r.text
            raise ProviderError(f"Ollama returned {r.status_code}: {str(msg)[:400]}")

        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                f"Ollama returned non-JSON response: {r.text[:200]}"
            ) from exc

        return data.get("message", {}).get("content", "")


# Static type assertion: OllamaProvider satisfies the Provider protocol.
_: type[Provider] = OllamaProvider  # type: ignore[assignment]
