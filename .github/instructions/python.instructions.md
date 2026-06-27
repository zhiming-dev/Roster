---
applyTo: "**/*.py"
---

# Python Authoring Instructions

Scope: the standalone runtime under `runtime/` (FastAPI + uvicorn + httpx + pyyaml, Python 3.10+).

## Goals

- Keep the runtime small, readable, and dependency-light.
- Match the existing module structure under `runtime/roster/`.
- Make agent/provider behavior explicit and observable.

## Design Rules

- Follow the existing package layout (`agent.py`, `bus.py`, `orchestrator.py`, `provenance.py`,
  `server.py`, `store.py`, `providers/`). Add new modules rather than overloading existing ones.
- Use type hints on public functions and dataclasses/pydantic models for structured payloads.
- Keep I/O (HTTP, SQLite, file system) at the edges; keep core logic pure where practical.
- Use `async`/`await` consistently — the server is async (FastAPI/uvicorn).
- Prefer the standard library; only add a dependency to `requirements.txt` when it earns its weight.

## Safety Rules

- Never hardcode credentials, endpoints, or model keys. Read them from
  `runtime/agents.config.yaml` (gitignored) — the committed template is
  `runtime/agents.config.example.yaml`.
- Do not log secrets or full prompts containing sensitive data.
- Preserve the append-only contract when writing `provenance.jsonl`.

## Quality Rules

- Keep functions short and single-purpose.
- Emit actionable errors with context, not bare exceptions.
- Validate JSON artifacts against `shared/schemas/*.schema.json` at the boundary.
- There is no test suite yet — if you add tests, use `pytest` and place them under `runtime/tests/`.
