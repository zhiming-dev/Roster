"""Default fallback to the repo's built-in agents (spec 003, FR-008 / SC-004).

A fresh clone ships only the committed ``agents.config.example.yaml`` (the live
``agents.config.yaml`` is gitignored). The runtime must still run the built-in team, and
the Setup editor must read that template while writes materialize a user-owned live config
without dirtying the committed example.
"""

from pathlib import Path

import yaml

from roster.config import EXAMPLE_CONFIG_NAME, load_config, resolve_config_path

_EXAMPLE = {
    "defaults": {
        "provider": "ollama",
        "endpoint": "http://localhost:11434",
        "model": "tinyllama:latest",
    },
    "search": {"enabled": True, "provider": "auto", "max_results": 5},
    "agents": {
        "planner": {"agent_file": "planner.agent.md", "role": "planner"},
        "researcher": {"agent_file": "researcher.agent.md", "role": "researcher", "tools": ["search"]},
    },
}


def _seed_example(base: Path) -> Path:
    """Write only the example template + its referenced .agent.md files (no live config)."""
    example = base / EXAMPLE_CONFIG_NAME
    example.write_text(yaml.safe_dump(_EXAMPLE, sort_keys=False), encoding="utf-8")
    for name in ("planner", "researcher"):
        (base / f"{name}.agent.md").write_text(
            f"---\ndescription: {name}\n---\n\nYou are the {name}.\n", encoding="utf-8"
        )
    return example


def test_resolve_falls_back_to_example_when_live_absent(tmp_path: Path):
    example = _seed_example(tmp_path)
    live = tmp_path / "agents.config.yaml"

    assert resolve_config_path(live) == example.resolve()


def test_resolve_prefers_live_when_present(tmp_path: Path):
    _seed_example(tmp_path)
    live = tmp_path / "agents.config.yaml"
    live.write_text(yaml.safe_dump(_EXAMPLE, sort_keys=False), encoding="utf-8")

    assert resolve_config_path(live) == live.resolve()


def test_load_config_runs_builtin_agents_on_fresh_clone(tmp_path: Path):
    _seed_example(tmp_path)
    live = tmp_path / "agents.config.yaml"
    assert not live.exists()

    cfg = load_config(live)

    assert set(cfg.agents) == {"planner", "researcher"}
    assert cfg.agents["planner"].role == "planner"
    assert "search" in cfg.agents["researcher"].tools


def test_editor_read_falls_back_but_write_materializes_live(tmp_path: Path, monkeypatch):
    example = _seed_example(tmp_path)
    live = tmp_path / "agents.config.yaml"
    monkeypatch.setenv("ROSTER_CONFIG", str(live))
    monkeypatch.delenv("CONCLAVE_CONFIG", raising=False)

    from roster import config_api

    # Read falls back to the committed example (built-in agents are listed).
    view = config_api.editable_config()
    assert {a["name"] for a in view["agents"]} == {"planner", "researcher"}
    assert next(a for a in view["agents"] if a["name"] == "planner")["is_planner"] is True

    # A write targets the live file (materialized), leaving the example untouched.
    config_api.update_search({"provider": "tavily"})
    assert live.is_file()
    assert yaml.safe_load(live.read_text(encoding="utf-8"))["search"]["provider"] == "tavily"
    assert yaml.safe_load(example.read_text(encoding="utf-8"))["search"]["provider"] == "auto"
