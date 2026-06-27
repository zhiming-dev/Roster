# AGENTS.md

> Entry point for any LLM coding agent (Copilot, Claude Code, Cursor, Aider, etc.) reading
> this repository. Read this file first.

## Session start reading order

Before doing repository work in a new chat session, read these in order:

1. [`.github/copilot-instructions.md`](./.github/copilot-instructions.md) — build/style conventions
2. [`.agent/instructions/collaboration-rules.instructions.md`](./.agent/instructions/collaboration-rules.instructions.md)
3. [`.agent/instructions/memory-bank.instructions.md`](./.agent/instructions/memory-bank.instructions.md)
4. [`.memory-bank/activeContext.md`](./.memory-bank/activeContext.md) and
   [`.memory-bank/learnings.md`](./.memory-bank/learnings.md)

Per-agent VS Code chat modes live in [`.github/chatmodes/`](./.github/chatmodes/) — one per Roster
role (Planner, Coder, QA, Reviewer, Researcher, E2E) plus a `repo-expert` Q&A mode.

## What this repo is

**Roster** — a human-in-the-loop, hierarchical multi-agent framework for software-engineering
and workflow automation. Architecture and rationale are in [`conclave-spec.md`](./conclave-spec.md).
A summary is in [`README.md`](./README.md).

The repo is **markdown-first**: agents and skills are plain markdown files with YAML frontmatter
plus reference docs. They can be loaded directly by any agent IDE (Copilot, Claude Code,
Cursor, Aider), and runs are materialized on disk under `runs/<run-id>/`.

There is also an optional **standalone runtime** in [`runtime/`](./runtime/) — a small Python
service that loads each `.agent.md` as a live agent backed by a local Ollama (or other provider),
exposes a principal-only chat with the Planner, and serves a live dashboard at
<http://localhost:8765/> showing every inter-agent message. Use the runtime when you want a
self-contained demo, an out-of-IDE control surface, or a reproducible target for the research
harness.

## Agents in this repo

| Path | Role | Status |
|---|---|---|
| [`planner-agent/planner.agent.md`](./planner-agent/planner.agent.md) | Planner / PM — decomposes goals into plans, dispatches, supervises | scaffolded · live in runtime |
| [`coder-agent/coder.agent.md`](./coder-agent/coder.agent.md) | Coder expert — implements changes per the plan | scaffolded · live in runtime |
| [`e2e-agent/e2e.agent.md`](./e2e-agent/e2e.agent.md) | E2E Test expert — Playwright browser tests; dispatched after the Coder | ✅ built · live in runtime |
| [`qa-agent/qa.agent.md`](./qa-agent/qa.agent.md) | QA / Validation expert — validates & fact-checks outputs against evidence | ✅ live in runtime |
| [`reviewer-agent/reviewer.agent.md`](./reviewer-agent/reviewer.agent.md) | Reviewer expert — reviews diffs, runs linters | scaffolded · live in runtime |
| [`researcher-agent/researcher.agent.md`](./researcher-agent/researcher.agent.md) | Researcher expert — web search + source-cited synthesis | 🌐 live in runtime (first agent with a real tool) |

## Shared contracts every agent depends on

- **Schemas** — [`shared/schemas/`](./shared/schemas/) — the source of truth for `Plan`, `Task`,
  `ActionProposal`, `AgentMessage`, `ProvenanceEvent`, `CapabilityGrant`.
- **Approval gate** — [`shared/approval-gate/SKILL.md`](./shared/approval-gate/SKILL.md) — risk-tier
  classification (T0–T4) and approval UX rules.
- **Provenance** — [`shared/provenance/SKILL.md`](./shared/provenance/SKILL.md) — the append-only
  event log format every agent writes to.
- **Council** — [`shared/council/SKILL.md`](./shared/council/SKILL.md) — optional cross-model
  deliberation protocol with anti-conformity safeguards.
- **Skill registry** — [`shared/skills.registry.yaml`](./shared/skills.registry.yaml)

## If the user asks you to start a new run

1. Generate a `run_id` (e.g. `run_YYYY-MM-DD_<short-hash>`).
2. Create `runs/<run_id>/goal.md` with the user's goal verbatim.
3. Invoke the **planner** (`planner-agent/planner.agent.md`) with that goal path.
4. The planner will produce `plan.draft.json` and **pause for human approval** — do not skip this
   gate, even if you believe you could plan and execute the work directly. The HITL gate is the
   point of the framework.

## If the user asks you to start the standalone runtime

1. `cd runtime`
2. `python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt`
3. Make sure `ollama serve` is running and the configured model is pulled (default
   `llama3.1:8b`).
4. `python -m roster` then open <http://localhost:8765/>.
5. The user chats with the **Planner only**. Do not surface sub-agents as conversational
   partners — they appear in the dashboard's event feed, not in the chat pane.

## If the user asks you to extend the framework

- New expert role → create `<role>-agent/<role>.agent.md` + `<role>-agent/<role>-runner/SKILL.md`
  following the QA agent's structure.
- New shared skill → add under `shared/<skill>/SKILL.md` and register in
  `shared/skills.registry.yaml`.
- Any schema change → update `shared/schemas/*.schema.json`, bump the schema `$id` version, and
  call out the breaking change in the PR description.

## Read-only zones (do not edit unless explicitly asked)

- `e2e-agent/e2e-test/test-definitions/**` and `e2e-agent/e2e-test/suites/**` — these are user
  test fixtures. Same rule as in [`e2e-agent/e2e-runner/SKILL.md`](./e2e-agent/e2e-runner/SKILL.md):
  let tests fail, do not silently edit them to match the page.
- `examples/**/provenance.sample.jsonl` — sample traces; treat as immutable reference data.
- `runs/<id>/provenance.jsonl` of an in-progress run — append only; never rewrite history.

## Conventions

- Every agent file: `<role>.agent.md` with frontmatter `description`, `tools`.
- Every skill file: `SKILL.md` with frontmatter `name`, `description`, `argument-hint`.
- All JSON artifacts validate against a schema in [`shared/schemas/`](./shared/schemas/).
- All times are ISO-8601 UTC.
- All ids are stable, URL-safe, and prefixed by kind: `plan_…`, `task_…`, `msg_…`, `evt_…`,
  `prop_…`, `run_…`.
