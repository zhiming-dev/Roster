# Feature Specification: Agent Setup Page (team configuration)

**Feature Branch**: `003-agent-setup-page`

**Created**: 2026-06-28

**Status**: Draft

**Input**: User description: "A Hermes/OpenClaw-style Setup page to configure the team of
subagents — add/remove agents, edit each agent's persona (system prompt), brain (provider /
model / API key), and tools; configure tool API keys (search). If the user configures nothing,
fall back to the codebase's built-in agents. Think about how configs / souls / personalities
are stored once productionalized."

## Context & Vision

The ultimate goal is a **team-collaboration Hermes**: the user curates a *team* of characterful
agents, each with a soul (persona), a brain (its own LLM), and capabilities (tools). Today agents
are hard-wired in `agents.config.yaml` + `*.agent.md` and only editable by hand. This feature adds
an in-app **Setup** view to manage the team, with config persisted in a way that is safe and
production-ready.

## Clarifications

### Session 2026-06-28

- Q: Where are non-secret agent profiles stored? → A: **File-based** — keep the live
  `agents.config.yaml` (brain/tools) and each agent's `.agent.md` body (persona); the Setup page
  reads/writes them. Git-friendly and consistent with the markdown-first design.
- Q: How are API keys stored? → A: **env / `.env`** — the UI writes keys to a gitignored `.env`;
  the YAML references them as `${VAR}`. Keys are write-only from the UI (never returned), and the
  running process picks them up immediately + on the next run.
- Q: How does the Setup page attach to the frontend? → A: **In-app view toggle** — a "Setup"
  button swaps the workspace to a settings panel (no router dependency).

## An Agent Profile (the model)

- **Soul** — name, role, `persona` (system prompt / personality). Lives in the agent's `.agent.md`
  body.
- **Brain** — provider, endpoint, model, options (temperature, max tokens), `api_key`
  (stored in `.env`, referenced as `${VAR}`). Lives in `agents.config.yaml`.
- **Capabilities** — tools (currently `search`) and **skills**. A skill is a named markdown
  procedure (a `SKILL.md` indexed in `shared/skills.registry.yaml`); granting a skill to an agent
  injects its content into that agent's system prompt (the runtime's "skill execution" — see the
  Skills section below). Stored as `skills: [...]` in the agent's `.agent.md` frontmatter.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Edit an agent's brain & persona (Priority: P1)

The user opens Setup, picks an agent, edits its persona, provider/model, options, and tools, sets
its API key, and saves. The change persists and applies to new chats.

**Independent Test**: Edit the researcher's model + persona, save, start a new chat; the runtime
uses the new model and prompt.

**Acceptance Scenarios**:

1. **Given** the Setup view, **When** the user edits an agent and saves, **Then** the change is
   written to `agents.config.yaml` / the agent's `.agent.md`, and a new chat uses it.
2. **Given** an API key entered in the UI, **When** saved, **Then** it is written to `.env` and the
   YAML references it as `${VAR}`; the key is never returned to the UI (only a "configured" badge).

### User Story 2 - Add / remove agents (Priority: P1)

The user adds a new specialist (name, role, persona, brain, tools) or removes one. The planner
cannot be removed.

**Acceptance Scenarios**:

1. **Given** Setup, **When** the user adds an agent, **Then** a new `.agent.md` + YAML entry are
   created and it appears in the roster.
2. **Given** Setup, **When** the user removes a non-planner agent, **Then** it is dropped from the
   roster. Removing the planner is rejected.

### User Story 3 - Configure tool keys & defaults / fall back to built-ins (Priority: P2)

The user sets the web-search provider + key (e.g. Tavily). If the user configures nothing, the
built-in agents (planner/coder/qa/researcher/…) from the repo are used as-is.

**Acceptance Scenarios**:

1. **Given** Setup, **When** the user sets the search provider to Tavily + a key, **Then** the key
   is written to `.env` and searches use Tavily.
2. **Given** a fresh install with no edits, **When** the runtime starts, **Then** it runs the
   built-in default agents.

### Edge Cases

- Inline (plaintext) API keys already in the YAML → a one-click "migrate keys to `.env`" moves them
  out and replaces with `${VAR}`.
- A key the UI sets must take effect for the running process (immediately) and persist.
- Editing config does not corrupt the YAML structure (defaults / queue / search / agents).
- Removing an agent that is mid-run → applies on the next chat, not retroactively.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose the editable team config (agents + their persona, brain,
  tools; global search) to the UI, with API keys redacted to a "configured" status.
- **FR-002**: The user MUST be able to edit an agent's persona, provider, endpoint, model, options,
  tools, and API key, and persist the change (YAML + `.agent.md` + `.env`).
- **FR-003**: API keys MUST be written to a gitignored `.env`, referenced from YAML as `${VAR}`,
  never returned to the UI, and applied to the running process immediately.
- **FR-004**: The user MUST be able to add and remove agents; the planner MUST NOT be removable.
- **FR-005**: The user MUST be able to set the web-search provider and key.
- **FR-006**: The system MUST provide a one-click migration of any inline YAML API keys to `.env`.
- **FR-007**: Config changes MUST apply to new chats (a Run rebuild), without requiring a manual
  file edit or full restart.
- **FR-008**: With no user configuration, the runtime MUST fall back to the repo's built-in agents.
- **FR-009**: The Setup view MUST be reachable via an in-app toggle (no router dependency).

### Key Entities

- **Agent profile**: name, role, persona, brain (provider/endpoint/model/options/key-ref), tools.
- **Secret**: a named key in `.env`, referenced as `${VAR}`; never surfaced.
- **Tool config**: global search (provider, key-ref, max results).

## Success Criteria *(mandatory)*

- **SC-001**: A user can change an agent's model + persona in the UI and a new chat uses them — no
  hand-editing of files.
- **SC-002**: An API key set in the UI is never visible in any API response; it lives only in
  `.env`.
- **SC-003**: Inline YAML keys can be migrated to `.env` in one click, leaving `${VAR}` references.
- **SC-004**: A fresh install with no edits runs the built-in agents.

## Skills (capability injection)

A skill is a markdown procedure (`SKILL.md`) indexed in `shared/skills.registry.yaml`. The
runtime does not run arbitrary code; "executing" a skill means **injecting its body into a
granting agent's system prompt** at load time (under a "## Skills you have" section, each body
capped to keep prompts bounded). The Setup editor offers the registry's skills as checkboxes per
agent, and the grant is persisted as `skills: [...]` in the agent's `.agent.md` frontmatter.

## Out of Scope

- Skill **code execution** / sandboxing — skills here are prompt-injected procedures, not
  runnable code.
- Multi-user / multi-tenant config; per-user secret isolation.
- A secrets manager / Vault (env/`.env` for now; the secret store is abstracted so it can grow).

## Productionalization note

`.env` + file-based config is the starting point; the secret access goes through a single
`set_env`/`${VAR}` seam so a future deployment can swap `.env` for a real secret store (Vault, OS
keychain, cloud secret manager) without touching profiles. Profiles stay file-based (git-friendly)
and can later be backed by a DB for multi-tenant use behind the same read/write API.

## Tasks

- [x] T001 Backend `config_api.py`: read editable config (key-redacted) + write agent/persona/
  search; `set_env` (write `.env` + live `os.environ`); `migrate_inline_keys`.
- [x] T002 `config.py`: load `.env` into the environment so `${VAR}` resolves at runtime.
- [x] T003 Endpoints: `GET /api/config`, `PUT/POST/DELETE /api/config/agents`,
  `PUT /api/config/search`, `POST /api/config/migrate-keys`; apply via `/api/reset`.
- [x] T004 Frontend Setup view (in-app toggle): agent cards, edit panel (persona, provider/model/
  options, tools, key), add/remove, search config, migrate-keys, "apply to new chat".
- [~] T005 Default fallback verified; docs updated.
- [x] T006 Skills: `config.py` loads `shared/skills.registry.yaml` + injects granted skill bodies
  into the agent system prompt (`agent.py`); `config_api` reads/writes `skills` in frontmatter +
  exposes the available registry; Setup editor multi-select + agent cards show granted skills.
