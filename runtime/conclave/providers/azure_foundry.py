"""Azure AI Foundry provider.

Calls an OpenAI-compatible *chat completions* endpoint. Three URL conventions are
auto-detected from the endpoint:

* **Azure OpenAI** (`*.openai.azure.com`):
  ``{endpoint}/openai/deployments/{deployment}/chat/completions?api-version=...``
  — auth via the ``api-key`` header.
* **Foundry v1 OpenAI-compatible** (path contains ``/openai/v1``), used by
  models-as-a-service deployments such as Grok, Llama, Mistral, etc.:
  ``{endpoint}/chat/completions`` (versionless — NO ``api-version``)
  — auth via ``Authorization: Bearer <key>``.
* **Foundry model inference** (e.g. `*.services.ai.azure.com`):
  ``{endpoint}/models/chat/completions?api-version=...`` with the deployment passed
  as the ``model`` field — auth via ``Authorization: Bearer <key>``.

The auth scheme is chosen automatically per the above, and can be forced with the
``auth`` config field (``auto`` | ``key`` | ``bearer``). The key is read from config —
typically ``api_key: ${AZURE_FOUNDRY_API_KEY}`` so it never lands in source control.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import ProviderConfig
from .base import Provider, ProviderError, merged_options

log = logging.getLogger("conclave.providers.azure_foundry")

_DEFAULT_API_VERSION = "2024-05-01-preview"


class AzureFoundryProvider:
    def __init__(self, cfg: ProviderConfig) -> None:
        self.cfg = cfg
        if not cfg.endpoint:
            raise ProviderError("azure_foundry: `endpoint` is required")
        if not cfg.target:
            raise ProviderError("azure_foundry: `deployment` (or `model`) is required")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(cfg.request_timeout_s, connect=10.0)
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- surface detection ----------------------------------------------------------

    @property
    def _is_v1_surface(self) -> bool:
        """The versionless `/openai/v1` OpenAI-compatible surface (Grok/MaaS et al.)."""
        return "/openai/v1" in self.cfg.endpoint.lower()

    @property
    def _is_azure_openai(self) -> bool:
        ep = self.cfg.endpoint.lower()
        return "openai.azure.com" in ep or "/openai/deployments/" in ep

    def _resolve_auth(self) -> str:
        mode = (self.cfg.auth or "auto").lower()
        if mode in ("key", "bearer"):
            return mode
        # auto: classic Azure OpenAI uses the api-key header; the versionless v1
        # surface and Foundry model-inference use OpenAI-style Bearer tokens.
        if self._is_azure_openai and not self._is_v1_surface:
            return "key"
        return "bearer"

    # -- URL / payload construction -------------------------------------------------

    def _effective_api_version(self) -> str | None:
        # The v1 surface is versionless — must NOT carry an api-version param.
        if self._is_v1_surface:
            return None
        return self.cfg.api_version or _DEFAULT_API_VERSION

    def _with_api_version(self, url: str) -> str:
        ver = self._effective_api_version()
        if not ver:
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}api-version={ver}"

    def _chat_url(self) -> str:
        ep = self.cfg.endpoint.rstrip("/")
        if ep.endswith("/chat/completions"):
            return self._with_api_version(ep)
        if self._is_v1_surface:
            return self._with_api_version(f"{ep}/chat/completions")
        if self._is_azure_openai:
            return self._with_api_version(
                f"{ep}/openai/deployments/{self.cfg.target}/chat/completions"
            )
        return self._with_api_version(f"{ep}/models/chat/completions")

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.cfg.api_key:
            if self._resolve_auth() == "bearer":
                headers["Authorization"] = f"Bearer {self.cfg.api_key}"
            else:
                headers["api-key"] = self.cfg.api_key
        return headers

    def _body(self, messages: list[dict[str, str]], kwargs: dict[str, Any]) -> dict[str, Any]:
        opts = merged_options(self.cfg, kwargs)
        body: dict[str, Any] = {"messages": messages}
        # The Foundry model-inference route requires `model`; Azure OpenAI ignores it.
        body["model"] = self.cfg.target
        if "temperature" in opts:
            body["temperature"] = opts["temperature"]
        # Accept either OpenAI-style `max_tokens` or Ollama-style `num_predict`.
        max_tokens = opts.get("max_tokens", opts.get("num_predict"))
        if max_tokens is not None:
            body["max_tokens"] = int(max_tokens)
        return body

    # -- Provider API ---------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        base = {
            "provider": "azure_foundry",
            "endpoint": self.cfg.endpoint,
            "model": self.cfg.target,
        }
        if not self.cfg.api_key:
            return {**base, "ok": False, "error": "no api_key configured",
                    "hint": "Set api_key: ${YOUR_ENV_VAR} in agents.config.yaml"}
        # A cheap reachability probe: 1-token completion.
        try:
            await self.chat(
                [{"role": "user", "content": "ping"}],
                options={"max_tokens": 1},
            )
            return {**base, "ok": True}
        except ProviderError as exc:
            return {**base, "ok": False, "error": str(exc)}

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        url = self._chat_url()
        try:
            r = await self._client.post(url, headers=self._headers(), json=self._body(messages, kwargs))
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Cannot reach Azure endpoint {self.cfg.endpoint}: {exc}"
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ProviderError(
                f"Azure request timed out after {self.cfg.request_timeout_s:.0f}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"HTTP error talking to Azure: {exc}") from exc

        if r.status_code in (401, 403):
            raise ProviderError(
                f"Azure auth failed ({r.status_code}) using {self._resolve_auth()!r} auth. "
                "Check the api_key, and that the auth scheme fits this endpoint: the "
                "`/openai/v1` surface (Grok/MaaS) needs Bearer, classic *.openai.azure.com "
                "needs key. Force it with `auth: bearer` or `auth: key` in the config."
            )
        if r.status_code == 404:
            raise ProviderError(
                f"Azure returned 404 for deployment '{self.cfg.target}'. Check the deployment "
                "name and api_version."
            )
        if r.status_code == 429:
            retry_after = _parse_retry_after(r)
            raise ProviderError(
                "Azure rate-limited this request (429)."
                + (f" Retry after ~{retry_after:.0f}s." if retry_after else "")
                + " Consider adding this agent to queue.require_queue.",
                retry_after=retry_after,
            )
        if r.status_code >= 400:
            raise ProviderError(f"Azure returned {r.status_code}: {_err_text(r)[:400]}")

        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Azure returned non-JSON response: {r.text[:200]}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"Azure response had no choices: {str(data)[:300]}")
        return choices[0].get("message", {}).get("content", "") or ""


def _parse_retry_after(r: httpx.Response) -> float | None:
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


_: type[Provider] = AzureFoundryProvider  # type: ignore[assignment]
