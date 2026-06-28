"""Provider package: factory + re-exports.

Existing imports (`from .providers import Provider, build_provider, ProviderError`)
keep working because they're re-exported here.
"""

from __future__ import annotations

from ..config import ProviderConfig
from .azure_foundry import AzureFoundryProvider
from .base import Provider, ProviderError
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

__all__ = [
    "Provider",
    "ProviderError",
    "OllamaProvider",
    "AzureFoundryProvider",
    "OpenAICompatProvider",
    "build_provider",
]


def build_provider(cfg: ProviderConfig) -> Provider:
    if cfg.provider == "ollama":
        return OllamaProvider(cfg)
    if cfg.provider == "azure_foundry":
        return AzureFoundryProvider(cfg)
    if cfg.provider == "openai_compatible":
        return OpenAICompatProvider(cfg)
    raise ValueError(
        f"Unknown provider '{cfg.provider}'. "
        "Supported: ollama, azure_foundry, openai_compatible."
    )
