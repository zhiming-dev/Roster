"""Read/write the live team configuration for the Setup UI (spec 003).

File-based per the decision: edits the live ``agents.config.yaml`` (brain/tools per agent),
each agent's ``.agent.md`` body (its persona/system prompt), and a gitignored ``.env`` for
secrets. **Secrets are never returned to the UI** — only a status — and are written to
``.env``, referenced from the YAML as ``${VAR}`` and pushed into ``os.environ`` so the live
process picks them up immediately.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .config import default_emoji, skills_registry

_PROVIDERS = ["ollama", "azure_foundry", "openai_compatible"]
_TOOLS = ["search"]
_SEARCH_PROVIDERS = ["auto", "duckduckgo", "tavily", "none"]


def _available_skills() -> list[dict[str, Any]]:
    reg = skills_registry(config_path().parent)
    return [
        {"name": n, "summary": e.get("summary", ""), "roles": e.get("applies_to_roles", [])}
        for n, e in reg.items()
    ]


def config_path() -> Path:
    raw = os.environ.get("ROSTER_CONFIG") or os.environ.get("CONCLAVE_CONFIG", "agents.config.yaml")
    return Path(raw).resolve()


def env_path() -> Path:
    return config_path().parent / ".env"


# -- raw YAML round-trip (keeps ${VAR} refs; does not expand env) --------------------

def _load_raw() -> dict[str, Any]:
    p = config_path()
    if not p.is_file():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _dump_raw(data: dict[str, Any]) -> None:
    config_path().write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


# -- .env secret store ---------------------------------------------------------------

def _read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    p = env_path()
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def set_env(key: str, value: str) -> None:
    """Persist a secret to .env AND apply it to the running process immediately."""
    env = _read_env()
    env[key] = value
    env_path().write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n", encoding="utf-8")
    os.environ[key] = value


def _key_status(value: Any) -> str:
    if not value:
        return "none"
    return "env" if str(value).startswith("${") else "inline"


# -- agent .md (frontmatter = identity/avatar; body = persona) -----------------------

def _persona_path(base: Path, agent: dict[str, Any]) -> Path | None:
    af = agent.get("agent_file")
    return (base / str(af)).resolve() if af else None


def read_md(path: Path | None) -> tuple[dict[str, Any], str]:
    if not path or not path.is_file():
        return {}, ""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return (yaml.safe_load(parts[1]) or {}), parts[2].lstrip("\n")
    return {}, text


def write_md(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True) if frontmatter else ""
    path.write_text(f"---\n{fm}---\n\n{body.rstrip()}\n", encoding="utf-8")


# -- read (key-redacted view for the UI) ---------------------------------------------

def editable_config() -> dict[str, Any]:
    raw = _load_raw()
    base = config_path().parent
    defaults = raw.get("defaults", {}) or {}
    agents: list[dict[str, Any]] = []
    for name, spec in (raw.get("agents") or {}).items():
        spec = spec or {}
        merged = {**defaults, **spec}
        opts = merged.get("options") or {}
        role = spec.get("role", name)
        fm, body = read_md(_persona_path(base, spec))
        agents.append(
            {
                "name": name,
                "role": role,
                "persona": body,
                "emoji": fm.get("emoji") or default_emoji(role),
                "color": fm.get("color"),
                "skills": fm.get("skills") or [],
                "provider": merged.get("provider"),
                "endpoint": merged.get("endpoint"),
                "model": merged.get("model"),
                "auth": merged.get("auth", "auto"),
                "options": {
                    "temperature": opts.get("temperature"),
                    "max_tokens": opts.get("max_tokens", opts.get("num_predict")),
                },
                "tools": [str(t).lower() for t in (merged.get("tools") or [])],
                "system_prompt_max_chars": merged.get("system_prompt_max_chars"),
                "key_status": _key_status(spec.get("api_key", merged.get("api_key"))),
                "is_planner": name == "planner",
            }
        )
    s = raw.get("search", {}) or {}
    search_key = "env" if os.environ.get("TAVILY_API_KEY") else _key_status(s.get("api_key"))
    return {
        "agents": agents,
        "search": {
            "enabled": bool(s.get("enabled", True)),
            "provider": s.get("provider", "auto"),
            "max_results": int(s.get("max_results", 5)),
            "key_status": search_key,
        },
        "available": {
            "providers": _PROVIDERS,
            "tools": _TOOLS,
            "search_providers": _SEARCH_PROVIDERS,
            "skills": _available_skills(),
        },
        "inline_keys": _count_inline_keys(raw),
    }


def _count_inline_keys(raw: dict[str, Any]) -> int:
    return sum(
        1
        for spec in (raw.get("agents") or {}).values()
        if _key_status((spec or {}).get("api_key")) == "inline"
    )


# -- write ---------------------------------------------------------------------------

def update_agent(name: str, patch: dict[str, Any]) -> None:
    raw = _load_raw()
    agents = raw.setdefault("agents", {})
    if name not in agents:
        raise KeyError(name)
    agent = agents[name] or {}
    base = config_path().parent

    pp = _persona_path(base, agent)
    if pp and any(k in patch for k in ("persona", "emoji", "color", "skills")):
        fm, body = read_md(pp)
        if patch.get("persona") is not None:
            body = str(patch["persona"])
        if "emoji" in patch:
            if patch["emoji"]:
                fm["emoji"] = patch["emoji"]
            else:
                fm.pop("emoji", None)
        if "color" in patch:
            if patch["color"]:
                fm["color"] = patch["color"]
            else:
                fm.pop("color", None)
        if "skills" in patch:
            fm["skills"] = [str(s) for s in (patch["skills"] or [])]
        write_md(pp, fm, body)

    for field in ("role", "provider", "endpoint", "model", "auth", "system_prompt_max_chars"):
        if field in patch:
            agent[field] = patch[field]
    if "tools" in patch:
        agent["tools"] = [str(t).lower() for t in (patch["tools"] or [])]
    if patch.get("options") is not None:
        agent["options"] = {k: v for k, v in patch["options"].items() if v is not None}
    if patch.get("api_key"):
        var = f"ROSTER_{name.upper()}_API_KEY"
        set_env(var, str(patch["api_key"]))
        agent["api_key"] = "${" + var + "}"

    agents[name] = agent
    _dump_raw(raw)


def add_agent(spec: dict[str, Any]) -> None:
    name = str(spec.get("name") or "").strip()
    if not name or not name.isidentifier():
        raise ValueError("agent name must be a simple identifier")
    raw = _load_raw()
    agents = raw.setdefault("agents", {})
    if name in agents:
        raise ValueError(f"agent '{name}' already exists")

    base = config_path().parent
    role = str(spec.get("role") or name)
    persona = str(spec.get("persona") or f"You are the {role} specialist of the Roster team.")
    tools = [str(t).lower() for t in (spec.get("tools") or [])]
    md_path = (base.parent / f"{name}-agent" / f"{name}.agent.md").resolve()
    md_path.parent.mkdir(parents=True, exist_ok=True)
    fm: dict[str, Any] = {
        "description": str(spec.get("description") or f"{role} agent"),
        "tools": tools,
    }
    if spec.get("emoji"):
        fm["emoji"] = spec["emoji"]
    if spec.get("color"):
        fm["color"] = spec["color"]
    if spec.get("skills"):
        fm["skills"] = [str(s) for s in spec["skills"]]
    write_md(md_path, fm, persona)

    agent: dict[str, Any] = {"agent_file": os.path.relpath(md_path, base), "role": role}
    for field in ("provider", "endpoint", "model", "auth"):
        if spec.get(field):
            agent[field] = spec[field]
    if tools:
        agent["tools"] = tools
    if spec.get("options"):
        agent["options"] = {k: v for k, v in spec["options"].items() if v is not None}
    if spec.get("api_key"):
        var = f"ROSTER_{name.upper()}_API_KEY"
        set_env(var, str(spec["api_key"]))
        agent["api_key"] = "${" + var + "}"
    agents[name] = agent
    _dump_raw(raw)


def delete_agent(name: str) -> None:
    if name == "planner":
        raise ValueError("the planner cannot be removed")
    raw = _load_raw()
    agents = raw.get("agents", {}) or {}
    if name not in agents:
        raise KeyError(name)
    agents.pop(name, None)
    raw["agents"] = agents
    _dump_raw(raw)


def update_search(patch: dict[str, Any]) -> None:
    raw = _load_raw()
    s = raw.setdefault("search", {})
    for field in ("enabled", "provider", "max_results"):
        if field in patch:
            s[field] = patch[field]
    if patch.get("api_key"):
        set_env("TAVILY_API_KEY", str(patch["api_key"]))
    _dump_raw(raw)


def migrate_inline_keys() -> int:
    """Move any inline (plaintext) agent api_key values into .env, leaving ${VAR} refs."""
    raw = _load_raw()
    moved = 0
    for name, spec in (raw.get("agents") or {}).items():
        spec = spec or {}
        value = spec.get("api_key")
        if value and _key_status(value) == "inline":
            var = f"ROSTER_{name.upper()}_API_KEY"
            set_env(var, str(value))
            spec["api_key"] = "${" + var + "}"
            raw["agents"][name] = spec
            moved += 1
    if moved:
        _dump_raw(raw)
    return moved
