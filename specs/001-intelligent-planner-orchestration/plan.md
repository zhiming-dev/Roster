# Implementation Plan: Intelligent Planner Orchestration

**Branch**: `001-intelligent-planner-orchestration` | **Date**: 2026-06-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-intelligent-planner-orchestration/spec.md`

## Summary

Replace the runtime's flat one-shot relay (planner emits one trailing `DISPATCH:` →
runtime runs one specialist → planner summarizes, capped at 3 hops) with a real
orchestration loop: **decompose → fan-out (parallel) → critique/verify → synthesize**, plus
**mid-task clarification** that suspends and resumes the same run, and **per-agent model
assignment** so a capable model (e.g. Opus) leads while cheap models (e.g. grok-mini) do
routine work. All changes live in the Python runtime (`runtime/roster/`); the React UI
(spec 002, US4) renders the new orchestration events. The human-in-the-loop gates,
no-fabrication rule, and append-only provenance are preserved and in fact strengthened.

## Technical Context

**Language/Version**: Python 3.10+ (runtime). No frontend changes here (002 consumes the
events).

**Primary Dependencies**: existing — FastAPI, httpx, PyYAML, the in-process `bus`, `LlmQueue`.
New — a generic OpenAI-compatible provider and (optionally) a native Anthropic provider under
`runtime/roster/providers/`.

**Storage**: existing SQLite event store (`store.py`) — extended only with new event *kinds*
(no schema change; events are JSON blobs). Run/plan artifacts may also be written under
`runs/<run-id>/` per the existing provenance convention.

**Testing**: none formal today (JSON validated against `shared/schemas/*.schema.json`). This
feature adds lightweight `pytest`-style unit tests for the new pure pieces (directive parser,
budget/state machine, critique-round accounting) — runnable without a live model.

**Target Platform**: local/self-hosted Python service; models via Ollama, Azure Foundry, or
the new OpenAI-compatible/Anthropic providers.

**Project Type**: backend service (the agent runtime) + an event contract consumed by the SPA.

**Performance Goals**: independent sub-tasks run concurrently (wall-clock ≈ slowest branch,
not the sum — SC-002); bounded rounds keep latency/cost predictable.

**Constraints**: HITL gates never bypassed; bounded fan-out and ≤2 critique rounds; no
fabrication; every orchestration step emitted as an event.

**Scale/Scope**: one active run; a handful of specialists; modest concurrency (queue
`max_concurrency` raised from 1 where backends allow).

## Constitution Check

*GATE: checked against [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
v1.0.0.*

| Principle | Bearing | Status |
|---|---|---|
| I. Human-in-the-loop | Adds mid-task `ASK`; T3/T4 still gated; planner never executes | ✅ strengthens |
| II. Safety & recoverability | Bounded fan-out + ≤2 critique rounds + caveated fallback; re-plan on failure | ✅ |
| III. Least privilege / restraint | Planner orchestrates only; specialists execute; grants unchanged | ✅ |
| IV. Truth over plausibility | The critique/verify loop exists specifically to catch fabrication before delivery | ✅ strengthens |
| V. Everything observable | New events: plan, dispatch, critique round, clarification | ✅ |
| VI. Typed, validated contracts | Decomposition validates against `shared/schemas/plan.schema.json`; new event kinds typed for the SPA | ✅ |

**Engineering-standard note (paid deps):** per-agent models may point at paid LLM endpoints
(Opus, grok). The constitution's "free/OSS unless approved" gate is satisfied — these are
operator-configured with operator-supplied keys and are the principal's explicit choice; the
zero-key local default (Ollama) remains. No violations → Complexity Tracking is empty.

## Research & Decisions (Phase 0)

| Decision | Choice | Rationale / alternatives |
|---|---|---|
| Turn protocol | The planner ends a turn with directive lines: optional `PLAN: <summary>`, then **one-or-more** `DISPATCH:<role>:<task>` (fan-out), **or** `ASK:<question>` (clarify), **or** none (final answer). | Generalizes today's single trailing `DISPATCH`. Keeps a text protocol weak models can follow; richer than JSON-only. Alt: strict JSON plan (brittle on small models) — kept as an optional structured mode for capable models. |
| Parallel execution | Run independent dispatches in one turn concurrently through `LlmQueue` with `max_concurrency>1`; gather all, feed back together. | `LlmQueue` already supports concurrency (`queue.py`); only the default of 1 and the single-line parser block it today. |
| Budget | 1 fan-out round + **≤2 critique/verify rounds** + 1 synthesis; `ASK` is free and suspends. | Replaces flat `MAX_DISPATCHES_PER_TURN=3`. Matches FR-010 (2 rounds/request). |
| Critique | After gather, the runtime injects a critique nudge; the planner self-triages and, for factual claims, escalates to `qa`/`reviewer`. Re-engaging the *same* specialist continues its thread. | FR-007–009/011 + the clarified "planner + qa" policy. Subagent histories already persist within a run (`agent.py`), enabling continuing threads. |
| Clarify + resume | Make `Run` a **resumable state machine**: `ASK` → `status=awaiting_input`, persist context, return the question; the next principal message resumes the *same* orchestration with all partial results intact. | FR-014–016a (v2 true suspend/resume). "Mid-fan-out" = between planner turns, with gathered partials retained. |
| `/api/chat` shape | Returns `{status: "done" | "awaiting_input", reply?/question?, runId}`. When `awaiting_input`, the next message is routed as the answer, not a new top-level turn. Live progress still streams over `/ws`. | Turns the one-shot blocking call (`server.py`) into a suspend/resume-aware endpoint. |
| Per-agent models | Add a generic **OpenAI-compatible** provider (xAI/grok, OpenAI, DeepSeek, Together, and Anthropic's OpenAI-compatible surface) and optionally a **native Anthropic** provider; register in `providers/build_provider`; config is already per-agent. | FR-012/013. Opus via the Anthropic provider or its OpenAI-compat endpoint — consult the `claude-api` skill at implementation time for model ids/params. |
| Decomposition artifact | The plan (sub-tasks + dependencies) validates against `shared/schemas/plan.schema.json` where feasible and is emitted as a `plan.proposed` event. | Constitution VI + FR-001. Capable models can emit structured plans; weak models fall back to the line protocol. |

## New event contract (Phase 1 — consumed by spec 002, US4)

Emitted on the existing `bus` (`{kind, ts, ...payload}`); persisted by `store.py` like the rest:

- `plan.proposed` — `{ runId, summary, tasks: [{id, role, task, dependsOn?}] }`
- `task.dispatched` — `{ from:"planner", to:role, task, round }` (also surfaced as `agent.message` `task_assignment` for back-compat)
- `task.result` — specialist output (already flows as `agent.message` `task_result`)
- `critique.round` — `{ round, concern, action: "re-dispatch"|"verify"|"accept", to?:role }`
- `clarification.requested` — `{ question }` (to principal; sets run `awaiting_input`)
- `clarification.answered` — `{ answer }`

These extend `frontend/src/types/events.ts` (002) so US4 renders decomposition, critique
rounds, and the awaiting-input prompt. No existing event kind changes.

## Run state machine (Phase 1 — core design)

```
idle ──principal msg──▶ planning ──▶ dispatching ──gather──▶ critiquing ──▶ synthesizing ──▶ idle
                                          │                       │
                                          └────────── ASK ────────┴──▶ awaiting_input ──answer──▶ (resume prior phase)
```

- `Run` holds: `status`, `round` counters (fan-out used, critique used), accumulated
  `gathered` context, and the `resume_phase` to return to after an answer.
- The planner's chat history (and each subagent's, within the run) already persists in memory,
  so resuming re-enters the loop with the answer as the next user turn — no replay needed for a
  live run. Cross-restart resume is best-effort via `resume_from_events` (already restores the
  planner transcript).
- Hard rules preserved: max fan-out width and `≤2` critique rounds; on exhaustion the planner
  must deliver a best-effort, uncertainty-flagged answer (FR-010).

## Project Structure

### Documentation (this feature)

```text
specs/001-intelligent-planner-orchestration/
├── spec.md              # done (clarified)
├── plan.md              # this file (Phase 0/1 inlined)
└── tasks.md             # next: /speckit-tasks
```

### Source Code (runtime)

```text
runtime/roster/
├── orchestrator.py      # rewrite the loop: decompose → fan-out → critique → synthesize;
│                        #   multi-DISPATCH + ASK parsing; budget/round accounting
├── run_state.py         # NEW: Run status + resumable state machine helpers
├── agent.py             # (reuse) per-run subagent history already enables continuing threads
├── providers/
│   ├── openai_compat.py # NEW: generic OpenAI-compatible provider (grok/OpenAI/DeepSeek/…)
│   ├── anthropic.py     # NEW (optional): native Anthropic provider for Opus
│   └── __init__.py      # register the new providers in build_provider
├── server.py            # /api/chat suspend/resume routing (awaiting_input)
├── bus.py               # (reuse) new event kinds need no code change
└── config.py            # (reuse) per-agent provider config already supported

shared/schemas/plan.schema.json   # (reuse) validate the decomposition
runs/<run-id>/                     # (reuse) provenance + plan artifacts
```

**Structure Decision**: All logic stays in `runtime/roster/`. The orchestrator is the main
change; the run state machine is factored into `run_state.py` for testability; providers are
isolated additions. The event contract is the seam to the 002 UI.

## Implementation Phases (maps to spec user stories)

- **Phase A — Model enabler (US3, P2, do first).** Add the OpenAI-compatible (+ optional
  Anthropic) provider and register it; document per-agent model config (planner→capable,
  searchers→cheap). *Why first:* US1/US2 quality depends on a capable planner; this is small and
  unblocks everything. (US1/US2 logic can still be built/tested against any existing capable
  backend, so this is recommended-early, not strictly blocking.)
- **Phase B — Decompose, fan-out, synthesize (US1, P1) 🎯.** New turn protocol (multi-DISPATCH),
  parallel execution via the queue, the `plan.proposed` event, and a templated synthesis step.
  Exit: SC-001 (multi-part deliverable) + SC-002 (concurrency).
- **Phase C — Critique & verification (US2, P1 flagship).** Post-gather critique nudge; planner
  self-triage; escalate factual claims to `qa`/`reviewer`; `≤2` rounds; `critique.round` events.
  Exit: SC-003 (≥80% injected-error detection on the test set).
- **Phase D — Mid-task clarification (US4, P3).** The resumable `Run` state machine, the `ASK`
  primitive, `clarification.*` events, and `/api/chat` suspend/resume. Exit: SC-004 (ask once,
  resume without restating).
- **Cross-cutting — Explainability.** Emit the new events throughout; coordinate with 002 US4 to
  render them (FR-017/018).

## Risks & Mitigations

- **Weak local model can't follow the richer protocol** → keep the line protocol simple; gate
  the structured-JSON plan behind capable models; Phase A makes a capable planner easy to
  configure.
- **Parallel calls overwhelm a shared backend** → `LlmQueue.max_concurrency` stays the throttle;
  per-agent backends avoid contention; default stays conservative.
- **Resume correctness** (the hard part) → factor into `run_state.py` with unit tests for the
  state transitions and budget accounting; rely on already-persistent in-run histories; treat
  cross-restart resume as best-effort and documented.
- **Critique loops oscillate** → hard `≤2` round bound, then a caveated answer (FR-010).
- **Event/UI drift** → define the event payloads here once; 002 types them in
  `events.ts`; keep them in sync via the shared list above.
- **Provider/key handling** → keys via env (`${VAR}`) only, never inline (existing `config.py`
  convention); zero-key Ollama default preserved.

## Complexity Tracking

*No constitution violations — table intentionally empty.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Next Steps

1. `/speckit-tasks` — break Phases A–D into ordered, independently-shippable tasks; the
   directive parser, budget/state machine, and critique accounting get unit tests (runnable
   without a live model). MVP = Phase A + B (a planner that decomposes, fans out in parallel,
   and synthesizes).
2. Coordinate the new event kinds with spec 002 US4 (the UI seams already exist).
