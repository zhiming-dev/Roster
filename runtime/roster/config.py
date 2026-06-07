"""Central configuration.

A single YAML file ([`agents.config.yaml`](../agents.config.yaml)) is the one place an
operator edits to point each agent at a model: provider, endpoint URL, model/deployment,
and API key. It also declares the shared **LLM queue** (`queue.require_queue`) used to
serialize agents that share one backend / API key.

Secrets are never written inline in the YAML in production: any string may reference an
environment variable with `${VAR}` or `${VAR:-default}` syntax, which is expanded at load
time. Per-agent overrides are available via `ROSTER_<AGENT>_<FIELD>` env vars, with
legacy `CONCLAVE_<AGENT>_<FIELD>` still accepted for compatibility.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("roster.config")

# ${VAR} or ${VAR:-default}
_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")

# Provider aliases → canonical name.
_PROVIDER_ALIASES = {
    "ollama": "ollama",
    "azure": "azure_foundry",
    "foundry": "azure_foundry",
    "azure_foundry": "azure_foundry",
    "azure-foundry": "azure_foundry",
    "azure_openai": "azure_foundry",
}


def _expand_env(value: Any) -> Any:
    """Recursively expand ${VAR} / ${VAR:-default} references in strings."""
    if isinstance(value, str):

        def repl(m: re.Match[str]) -> str:
            var, default = m.group(1), m.group(2)
            return os.environ.get(var, default if default is not None else "")

        return _ENV_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


@dataclass
class ProviderConfig:
    """How one agent reaches its model. Provider-agnostic superset of fields."""

    provider: str
    endpoint: str
    model: str
    options: dict[str, Any] = field(default_factory=dict)
    keep_alive: str | None = None
    request_timeout_s: float = 120.0
    # Azure AI Foundry / Azure OpenAI / OpenAI-compatible:
    api_key: str | None = None
    api_version: str | None = None
    deployment: str | None = None
    auth: str = "auto"  # auto | key | bearer

    @property
    def target(self) -> str:
        """The model identifier to display/send: deployment for Azure, model for Ollama."""
        return self.deployment or self.model

    def public_dict(self) -> dict[str, Any]:
        """Serializable view with secrets stripped — safe to send to the dashboard."""
        return {
            "provider": self.provider,
            "endpoint": self.endpoint,
            "model": self.target,
            "auth": "none" if not self.api_key else self.auth,
        }


@dataclass
class QueueConfig:
    """Shared LLM queue. Agents in `require_queue` must serialize through it."""

    max_concurrency: int = 1
    require_queue: list[str] = field(default_factory=list)


@dataclass
class SearchConfig:
    """Web-search tool configuration (the runtime's first real tool)."""

    enabled: bool = True
    provider: str = "auto"  # auto | duckduckgo | tavily | none
    api_key: str | None = None
    max_results: int = 5


@dataclass
class AgentConfig:
    name: str
    role: str
    agent_file: Path
    description: str
    system_prompt: str
    provider: ProviderConfig
    system_prompt_max_chars: int | None = None
    tools: list[str] = field(default_factory=list)  # e.g. ["search"]


@dataclass
class RuntimeConfig:
    agents: dict[str, AgentConfig]
    queue: QueueConfig
    search: SearchConfig


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _parse_agent_md(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    frontmatter = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n")
    return frontmatter, body


def _env_override(agent: str, field_name: str, fallback: Any) -> Any:
    roster_key = f"ROSTER_{agent.upper()}_{field_name.upper()}"
    legacy_key = f"CONCLAVE_{agent.upper()}_{field_name.upper()}"
    return os.environ.get(roster_key, os.environ.get(legacy_key, fallback))


def _build_provider(name: str, merged: dict[str, Any]) -> ProviderConfig:
    raw_provider = str(_env_override(name, "provider", merged.get("provider", "ollama")))
    provider = _PROVIDER_ALIASES.get(raw_provider.lower())
    if provider is None:
        raise ValueError(
            f"agent '{name}': unknown provider '{raw_provider}'. "
            f"Supported: {sorted(set(_PROVIDER_ALIASES.values()))}"
        )

    endpoint = str(_env_override(name, "endpoint", merged.get("endpoint", "")))
    model = str(_env_override(name, "model", merged.get("model", "")))
    api_key = _env_override(name, "api_key", merged.get("api_key"))
    deployment = _env_override(name, "deployment", merged.get("deployment"))
    auth = str(_env_override(name, "auth", merged.get("auth", "auto")))

    cfg = ProviderConfig(
        provider=provider,
        endpoint=endpoint,
        model=model,
        options=dict(merged.get("options") or {}),
        keep_alive=merged.get("keep_alive"),
        request_timeout_s=float(merged.get("request_timeout_s", 120.0)),
        api_key=str(api_key) if api_key else None,
        api_version=merged.get("api_version"),
        deployment=str(deployment) if deployment else None,
        auth=auth.lower(),
    )

    # Validate early with actionable messages, but don't crash the whole server —
    # surface as a warning so the dashboard health check can report the bad agent.
    if provider == "azure_foundry":
        if not cfg.endpoint:
            log.warning("agent '%s': azure_foundry requires `endpoint`", name)
        if not cfg.target:
            log.warning("agent '%s': azure_foundry requires `deployment` (or `model`)", name)
        if not cfg.api_key:
            log.warning(
                "agent '%s': azure_foundry has no api_key — set `api_key: ${YOUR_ENV_VAR}`",
                name,
            )
    elif provider == "ollama":
        if not cfg.endpoint:
            log.warning("agent '%s': ollama requires `endpoint`", name)
        if not cfg.model:
            log.warning("agent '%s': ollama requires `model`", name)

    return cfg


def load_config(config_path: str | Path) -> RuntimeConfig:
    config_path = Path(config_path).resolve()
    raw = _expand_env(yaml.safe_load(config_path.read_text(encoding="utf-8")) or {})
    defaults = raw.get("defaults", {}) or {}
    base_dir = config_path.parent

    q = raw.get("queue", {}) or {}
    queue = QueueConfig(
        max_concurrency=max(1, int(q.get("max_concurrency", 1))),
        require_queue=list(q.get("require_queue", []) or []),
    )

    s = raw.get("search", {}) or {}
    search = SearchConfig(
        enabled=bool(s.get("enabled", True)),
        provider=str(s.get("provider", "auto")),
        # Convenience: fall back to TAVILY_API_KEY without forcing it into the YAML.
        api_key=(s.get("api_key") or os.environ.get("TAVILY_API_KEY")) or None,
        max_results=int(s.get("max_results", 5)),
    )

    agents: dict[str, AgentConfig] = {}
    for name, spec in (raw.get("agents") or {}).items():
        merged = _merge(defaults, spec or {})
        if "agent_file" not in merged:
            raise ValueError(f"agent '{name}': missing required `agent_file`")
        agent_file = (base_dir / merged["agent_file"]).resolve()
        frontmatter, body = _parse_agent_md(agent_file)

        cap = merged.get("system_prompt_max_chars")
        if cap is not None and len(body) > int(cap):
            body = body[: int(cap)].rstrip() + "\n\n... [trimmed for runtime] ...\n"

        tools = [str(t).lower() for t in (merged.get("tools") or [])]

        agents[name] = AgentConfig(
            name=name,
            role=merged.get("role", name),
            agent_file=agent_file,
            description=str(frontmatter.get("description", "")),
            system_prompt=body,
            provider=_build_provider(name, merged),
            system_prompt_max_chars=int(cap) if cap is not None else None,
            tools=tools,
        )

    # Validate queue membership references real agents.
    for member in queue.require_queue:
        if member not in agents:
            log.warning(
                "queue.require_queue lists unknown agent '%s' (known: %s)",
                member,
                ", ".join(agents) or "<none>",
            )

    return RuntimeConfig(agents=agents, queue=queue, search=search)
