"""Provider abstraction shared by all backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..config import ProviderConfig


class ProviderError(RuntimeError):
    """Raised when a provider call fails in a way the orchestrator should surface.

    Carries an optional `retry_after` (seconds) for rate-limit (429) responses.
    """

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@runtime_checkable
class Provider(Protocol):
    cfg: ProviderConfig

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...

    async def health(self) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


def merged_options(cfg: ProviderConfig, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Combine config-level options with per-call overrides."""
    return {**cfg.options, **(kwargs.get("options") or {})}
