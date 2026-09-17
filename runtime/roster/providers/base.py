"""Provider abstraction shared by all backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..config import ProviderConfig


class ProviderError(RuntimeError):
    """Raised when a provider call fails in a way the orchestrator should surface.

    ``retriable`` marks transient failures (429 rate limits, timeouts, 5xx) that the
    agent loop may retry with backoff; ``retry_after`` carries the server's requested
    wait (seconds) when it sent one.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        retriable: bool = False,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.retriable = retriable


def content_filter_detail(body: object) -> str | None:
    """Detect a provider-side content-filter block in a parsed response body.

    Azure (and compatible backends) signal it two ways: a top-level error with
    ``code: content_filter``, or a choice with ``finish_reason: content_filter`` and an
    empty message. Returns the filter's own message when found, else ``None``.
    """
    if not isinstance(body, dict):
        return None
    err = body.get("error")
    if isinstance(err, dict) and "content_filter" in str(err.get("code", "")).lower():
        return str(err.get("message") or "response blocked by content filter")
    for ch in body.get("choices") or []:
        if isinstance(ch, dict) and ch.get("finish_reason") == "content_filter":
            cfr = ch.get("content_filter_results")
            if isinstance(cfr, dict):
                e = cfr.get("error")
                if isinstance(e, dict) and e.get("message"):
                    return str(e["message"])
            return "finish_reason=content_filter"
    return None


def content_filter_error(provider_label: str, detail: str) -> "ProviderError":
    """A clean, actionable error for a content-filter block — instead of a raw JSON dump.

    Known failure mode (first seen 2026-07-01): Azure Prompt Shields misfires on the
    agent tool-protocol prompt with label 'Jailbreak'. Deterministic, so not retriable —
    the fix is an operator setting, not another attempt.
    """
    return ProviderError(
        f"{provider_label} content filter blocked this exchange: {detail[:200]} — this is a "
        "provider-side safety filter misfiring on the agent's tool-protocol prompt, NOT a "
        "problem with the task, and retrying the same request will fail the same way. "
        "Operator fix: in the Azure AI Foundry portal, set this deployment's jailbreak / "
        "indirect-attack Prompt Shields to 'Annotate only'. A shorter or reworded task "
        "brief sometimes avoids the trigger."
    )


@runtime_checkable
class Provider(Protocol):
    cfg: ProviderConfig

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...

    async def health(self) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


def merged_options(cfg: ProviderConfig, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Combine config-level options with per-call overrides."""
    return {**cfg.options, **(kwargs.get("options") or {})}
