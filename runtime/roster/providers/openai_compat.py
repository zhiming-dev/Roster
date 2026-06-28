"""Generic OpenAI-compatible chat-completions provider.

One provider for every backend that speaks the OpenAI `/chat/completions` schema with a
Bearer key — xAI (grok), OpenAI, DeepSeek, Together, Groq, and Anthropic's OpenAI-compatible
surface. This is what makes per-agent model assignment cheap: point the planner at a capable
model and a searcher at a cheap one, each via its own `endpoint` + `api_key`.

Config:
    provider: openai_compatible   # or aliases: openai, xai, grok, deepseek, anthropic, claude
    endpoint: https://api.x.ai/v1 # base URL (…/chat/completions appended) or a full URL
    model: grok-2-mini            # the model id the backend expects
    api_key: ${XAI_API_KEY}       # Bearer key — never inline, always ${ENV_VAR}
    options: { temperature: 0.2, max_tokens: 1000 }
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import ProviderConfig
from .base import Provider, ProviderError, merged_options

log = logging.getLogger("roster.providers.openai_compat")


class OpenAICompatProvider:
    def __init__(self, cfg: ProviderConfig) -> None:
        self.cfg = cfg
        if not cfg.endpoint:
            raise ProviderError("openai_compatible: `endpoint` (base URL) is required")
        if not cfg.target:
            raise ProviderError("openai_compatible: `model` is required")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(cfg.request_timeout_s, connect=10.0)
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _chat_url(self) -> str:
        ep = self.cfg.endpoint.rstrip("/")
        return ep if ep.endswith("/chat/completions") else f"{ep}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        return headers

    def _body(self, messages: list[dict[str, str]], kwargs: dict[str, Any]) -> dict[str, Any]:
        opts = merged_options(self.cfg, kwargs)
        body: dict[str, Any] = {"model": self.cfg.target, "messages": messages}
        if "temperature" in opts:
            body["temperature"] = opts["temperature"]
        # Accept OpenAI-style `max_tokens` or Ollama-style `num_predict`.
        max_tokens = opts.get("max_tokens", opts.get("num_predict"))
        if max_tokens is not None:
            body["max_tokens"] = int(max_tokens)
        return body

    async def health(self) -> dict[str, Any]:
        base = {
            "provider": "openai_compatible",
            "endpoint": self.cfg.endpoint,
            "model": self.cfg.target,
        }
        if not self.cfg.api_key:
            return {
                **base,
                "ok": False,
                "error": "no api_key configured",
                "hint": "Set api_key: ${YOUR_ENV_VAR} in agents.config.yaml",
            }
        try:
            await self.chat([{"role": "user", "content": "ping"}], options={"max_tokens": 1})
            return {**base, "ok": True}
        except ProviderError as exc:
            return {**base, "ok": False, "error": str(exc)}

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        try:
            r = await self._client.post(
                self._chat_url(), headers=self._headers(), json=self._body(messages, kwargs)
            )
        except httpx.ConnectError as exc:
            raise ProviderError(f"Cannot reach {self.cfg.endpoint}: {exc}") from exc
        except httpx.ReadTimeout as exc:
            raise ProviderError(
                f"Request to {self.cfg.endpoint} timed out after {self.cfg.request_timeout_s:.0f}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"HTTP error talking to {self.cfg.endpoint}: {exc}") from exc

        if r.status_code in (401, 403):
            raise ProviderError(
                f"Auth failed ({r.status_code}) for {self.cfg.endpoint}. Check the api_key."
            )
        if r.status_code == 404:
            raise ProviderError(
                f"{self.cfg.endpoint} returned 404 for model '{self.cfg.target}'. "
                "Check the model id and the base URL."
            )
        if r.status_code == 429:
            retry_after = _retry_after(r)
            raise ProviderError(
                f"{self.cfg.endpoint} rate-limited this request (429)."
                + (f" Retry after ~{retry_after:.0f}s." if retry_after else "")
                + " Consider adding this agent to queue.require_queue.",
                retry_after=retry_after,
            )
        if r.status_code >= 400:
            raise ProviderError(f"{self.cfg.endpoint} returned {r.status_code}: {_err_text(r)[:400]}")

        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Non-JSON response from {self.cfg.endpoint}: {r.text[:200]}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"Response had no choices: {str(data)[:300]}")
        return choices[0].get("message", {}).get("content", "") or ""


def _retry_after(r: httpx.Response) -> float | None:
    val = r.headers.get("retry-after")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _err_text(r: httpx.Response) -> str:
    try:
        body = r.json()
        if isinstance(body, dict) and "error" in body:
            err = body["error"]
            return err.get("message", str(err)) if isinstance(err, dict) else str(err)
        return str(body)
    except Exception:  # noqa: BLE001
        return r.text


_: type[Provider] = OpenAICompatProvider  # type: ignore[assignment]
