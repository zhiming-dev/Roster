---
description: "Task list — Intelligent Planner Orchestration"
---

# Tasks: Intelligent Planner Orchestration

**Input**: Design documents in `specs/001-intelligent-planner-orchestration/`
([spec.md](./spec.md), [plan.md](./plan.md))

**Gate**: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) v1.0.0 — passed
in plan.md.

**Tests**: The plan calls for unit tests on the *pure* pieces only — the directive parser, the
run state machine / budget accounting, and critique-round accounting. These run without a live
model and are included below; broader model-dependent behavior is verified manually / via the
research harness.

## Format: `[ID] [P?] [Story] Description`

- **[P]** = parallelizable (different files, no dependency on another unchecked task).
- **[Story]** = US1 (decompose/fan-out/synthesize) · US2 (critique) · US3 (per-agent models) ·
  US4 (mid-task clarify).
- Paths are relative to repo root; runtime code is under `runtime/roster/`.

---

## Phase 1: Setup

- [x] T001 [P] Pytest dev setup: `runtime/requirements-dev.txt` (pytest, pytest-asyncio),
  `runtime/tests/__init__.py`, and a `pytest` config (in `runtime/pyproject.toml` or
  `pytest.ini`); a trivial import smoke test.
- [x] T002 [P] Single source for the new event contract: `runtime/roster/events.py` with kind
  constants and payload docstrings (`plan.proposed`, `task.dispatched`, `critique.round`,
  `clarification.requested`, `clarification.answered`) — mirrored by spec 002's `events.ts`.

---

## Phase 2: Foundational (blocking prerequisites)

**⚠️ No user-story phase begins until this is complete.**

- [x] T003 `runtime/roster/run_state.py` — NEW: `RunStatus` enum
  (`idle|planning|dispatching|critiquing|synthesizing|awaiting_input`), an `OrchestrationState`
  (counters `fanouts_used`, `critique_used`; `gathered` context; `resume_phase`) and pure
  budget/transition helpers (`can_fanout`, `can_critique`, `note_critique`, `suspend`, `resume`).
- [x] T004 Directive parser (now `protocol.py`, imported by `orchestrator.py`) (replaces `_parse_dispatch`): parse a planner
  reply into `PlannerTurn { plan_summary?, dispatches: [(role, task)], ask?, final_text }`,
  supporting **multiple** `DISPATCH:` lines, one optional `ASK:`, and an optional `PLAN:` line.
  Pure / no I/O.
- [x] T005 [P] Event emit helpers in `events.py`: thin wrappers over `bus.publish` + `prov.emit`
  for each new kind (`emit_plan_proposed`, `emit_task_dispatched`, `emit_critique_round`,
  `emit_clarification_requested`, `emit_clarification_answered`).
- [x] T006 [P] Unit tests in `runtime/tests/`: directive parser (T004) — multi-dispatch, ASK,
  PLAN, plain final — and run-state budget/transitions (T003).

**Checkpoint**: shared orchestration primitives exist and are unit-tested (no live model needed).

---

## Phase 3: User Story 3 — Per-agent model assignment (Priority: P2, enabler — do early)

**Goal**: Assign a distinct LLM per agent (capable planner, cheap searchers).

**Independent Test**: Configure two agents with two providers; one request; confirm from the run
record each used its assigned model (SC-006).

- [x] T007 [P] [US3] `runtime/roster/providers/openai_compat.py` — generic OpenAI-compatible
  `Provider` (chat completions; `base_url` + key) covering xAI/grok, OpenAI, DeepSeek, Together,
  and Anthropic's OpenAI-compatible surface. Implement `chat`, `health`, `aclose` per `base.py`.
- [ ] T008 [P] [US3] `runtime/roster/providers/anthropic.py` (optional) — native Anthropic
  provider for Opus. Consult the `claude-api` skill for model ids, headers, and params.
- [x] T009 [US3] Register both in `providers/__init__.build_provider` and add config aliases in
  `config.py` (`openai`, `openai_compatible`, `xai`/`grok`, `anthropic`/`claude`).
- [x] T010 [US3] Document per-agent model config in `runtime/agents.config.example.yaml`
  (planner → capable model; researcher/qa → cheap), preserving the zero-key Ollama default.
- [x] T011 [US3] Surface a misconfigured per-agent provider on `/api/health` (reuse the existing
  startup health path in `server.py`/`agent.health`).

**Checkpoint**: SC-006 — one request spanning ≥2 different models/providers.

---

## Phase 4: User Story 1 — Decompose, fan-out, synthesize (Priority: P1) 🎯 MVP

**Goal**: Turn the one-shot relay into decompose → parallel fan-out → synthesize.

**Independent Test**: The NASDAQ 10/30/200-day request yields one deliverable with a distinct,
specialist-sourced section per timeframe (SC-001), independent branches running concurrently
(SC-002).

- [x] T012 [US1] Rewrite `Run.handle_principal_message` into the orchestration loop using
  `run_state` + the directive parser (planning turn → collect dispatches); retire the flat
  `MAX_DISPATCHES_PER_TURN` cap in favor of the round budget.
- [x] T013 [US1] Parallel fan-out: run a turn's dispatches concurrently via `LlmQueue`
  (`asyncio.gather`), raise default `queue.max_concurrency` where backends allow, gather results
  and feed them back together with per-role prefixes.
- [x] T014 [US1] Emit `plan.proposed` from the planning turn; validate against
  `shared/schemas/plan.schema.json` when the planner emits structured tasks, else derive the plan
  from the dispatch set.
- [~] T015 [US1] Templated synthesis turn (higher token budget) that addresses every requested
  part; enforce a max fan-out width.
- [x] T016 [US1] Update `build_planner_suffix` for the new protocol (multi-DISPATCH, PLAN, fan-out
  vs direct answer), preserving direct answers for simple messages (FR-006).
- [x] T017 [P] [US1] Unit test: the loop drives an N-way fan-out + synthesis against a fake
  provider/agent (no live model), asserting concurrency and that all branches are folded in.

**Checkpoint**: SC-001 + SC-002. **MVP = Phase 3 + Phase 4.**

---

## Phase 5: User Story 2 — Critique & verification (Priority: P1, flagship)

**Goal**: The planner critiques specialist output and pushes back before answering.

**Independent Test**: A specialist result with an injected inconsistency triggers a critique
round rather than being delivered as-is (SC-003).

- [x] T018 [US2] Post-gather critique nudge: after results return, inject "critically evaluate for
  consistency/plausibility; escalate factual claims to qa/reviewer"; track `critique_used`.
- [x] T019 [US2] Re-engage flows: planner may re-DISPATCH to the *same* specialist (continuing its
  in-run thread) or to `qa`/`reviewer`, then reconcile the verifier's finding.
- [x] T020 [US2] Enforce the **≤2 critique rounds** bound; on exhaustion force a best-effort,
  uncertainty-flagged answer (FR-010).
- [x] T021 [US2] Emit `critique.round` events (`concern`, `action`, `to?`).
- [x] T022 [P] [US2] Unit test: an injected-inconsistency result (fake) makes the loop open a
  critique round instead of finalizing.

**Checkpoint**: SC-003 (≥80% injected-error detection on the controlled set).

---

## Phase 6: User Story 4 — Mid-task clarification with resume (Priority: P3)

**Goal**: Planner asks the principal mid-task and resumes the same run (v2 suspend/resume).

**Independent Test**: An ambiguous request → planner asks once → after a one-line answer the
original task completes without restating (SC-004).

- [x] T023 [US4] `ASK:` handling in the loop: set `status=awaiting_input`, save `resume_phase`,
  emit `clarification.requested`, and return the question.
- [x] T024 [US4] `/api/chat` suspend/resume in `server.py`: response carries
  `{status: "done"|"awaiting_input", reply?|question?, runId}`; when the active run is
  `awaiting_input`, route the next message as the answer (emit `clarification.answered`).
- [x] T025 [US4] Resume path: re-enter the loop at `resume_phase` with the answer as the next
  turn, retaining gathered partials (in-run histories already persist); best-effort cross-restart
  via `resume_from_events`.
- [x] T026 [P] [US4] Unit test: `ASK` suspends (status=awaiting_input) and a following answer
  resumes and completes without restarting.

**Checkpoint**: SC-004.

---

## Phase 7: Polish & cross-cutting

- [ ] T027 Wire the new event kinds into spec 002: extend `frontend/src/types/events.ts` and the
  US4 components (`PlanView`, `CritiqueRound`, `ClarificationPrompt`) to render plan / critique /
  clarification.
- [ ] T028 [P] Docs: update `runtime/agents.config.example.yaml` comments and `runtime/README.md`
  for the new protocol, round budgets, and per-agent models.
- [ ] T029 [P] Provenance: ensure every new transition (plan, dispatch, critique, clarification)
  is emitted to `runs/<id>/provenance.jsonl` (constitution V).
- [ ] T030 Tune defaults: max fan-out width, `queue.max_concurrency`, and planner/synthesis token
  caps.

---

## Dependencies & Execution Order

- **Setup (T001–T002)**: no deps; parallel.
- **Foundational (T003–T006)**: depends on Setup; **blocks all user stories**. T003/T004 before
  their tests (T006); T005 parallel.
- **US3 (T007–T011)**: depends on Foundational only. Recommended **first** (a capable planner
  lifts US1/US2 quality), but independent — US1/US2 can be built against any existing capable
  backend (e.g. azure_foundry) in parallel if staffed. T007/T008 parallel.
- **US1 (T012–T017)**: depends on Foundational. T012 before T013–T015; T016 prompt anytime;
  T017 after the loop exists.
- **US2 (T018–T022)**: depends on US1 (critique runs on gathered results).
- **US4 (T023–T026)**: depends on US1 (suspend/resume wraps the loop) + the `ASK` directive
  (T004). Can follow US2 or proceed in parallel if staffed.
- **Polish (T027–T030)**: after the relevant stories; T027 coordinates with spec 002 US4.

### Within each story

- Pure helpers (parser, state machine) and their unit tests before the loop wiring.
- The loop (US1) before critique (US2) and before suspend/resume (US4).
- A story's checkpoint (its SC) is met before moving to the next priority.
- **MVP = Phase 3 (providers) + Phase 4 (US1)**: a planner that decomposes, fans out in parallel,
  and synthesizes. US2 adds the critique loop; US4 adds mid-task clarification.
