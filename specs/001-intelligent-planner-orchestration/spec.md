# Feature Specification: Intelligent Planner Orchestration

**Feature Branch**: `001-intelligent-planner-orchestration`

**Created**: 2026-06-26

**Status**: Draft

**Input**: User description: "Make the Planner genuinely intelligent — analyze a request,
decompose it, route sub-tasks to the right specialists (each potentially on a different
LLM), critique/verify specialist output before answering (agents discussing each other's
work), and ask the principal clarifying questions mid-task and then *resume* rather than
restart — all surfaced in an explainable, team-collaboration UI. The Planner acts as a CEO:
it never executes domain work itself."

## Context & Problem

Today a complex request (e.g. *"analyze today's NASDAQ trend and produce a 10-day, 30-day,
and 200-day report"*) produces a shallow result: the Planner forwards a single one-line task
to one specialist, the specialist runs one search, and the Planner summarizes whatever comes
back. The runtime executes a flat, one-shot relay — it does not decompose, does not route to
multiple specialists, does not critique results, and cannot ask a question and continue. The
elaborate planning/dispatch design in the agent definitions is not realized by the runtime.

This feature makes the Planner an actual orchestrator and the agents a collaborating team.

## Clarifications

### Session 2026-06-26

- Q: How deep should mid-task clarification (US4) go? → A: **v2 — true suspend/resume.** The
  run becomes a resumable state machine; the Planner may pause at any point, including
  mid-fan-out, ask the principal, and resume the same in-flight orchestration with partial
  results intact. (Resolves FR-016.)
- Q: Who performs critique/verification (US2)? → A: **Two-layered — Planner + QA.** The Planner
  self-triages every result; factual claims needing independent confirmation escalate to a
  dedicated QA/reviewer specialist. (Resolves FR-011.)
- Q: How many critique/verification rounds before forcing an answer? → A: **2 rounds per
  request**, then a best-effort, uncertainty-flagged answer. (Resolves FR-010.)
- Q: Detection target for the injected-error test? → A: **≥ 80% of trials.** (Resolves SC-003.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Decompose, route to specialists, and synthesize (Priority: P1)

The principal gives the Planner a multi-part, non-trivial goal. The Planner analyzes it,
breaks it into the smallest sensible set of sub-tasks, routes each to the specialist whose
expertise fits, runs independent sub-tasks concurrently, and synthesizes one structured
deliverable that addresses **every** part of the request.

**Why this priority**: This is the core complaint and the foundation everything else builds
on. Without real decomposition there is nothing to route, critique, or explain. Delivers the
single most visible jump in apparent intelligence.

**Independent Test**: Submit the NASDAQ 10/30/200-day request. Verify the deliverable
contains a clearly-labelled section for each timeframe, each backed by specialist work
(sourced facts), rather than one undifferentiated paragraph.

**Acceptance Scenarios**:

1. **Given** a request with three distinct sub-questions, **When** the Planner processes it,
   **Then** it produces an inspectable decomposition listing at least the three sub-tasks
   before any specialist is invoked.
2. **Given** independent sub-tasks, **When** they are dispatched, **Then** they execute
   concurrently and the run does not serialize them needlessly.
3. **Given** all specialist results have returned, **When** the Planner replies, **Then** the
   final deliverable explicitly addresses each part of the original request.
4. **Given** a simple conversational message (greeting, status question), **When** the Planner
   processes it, **Then** it answers directly with no decomposition or dispatch.

---

### User Story 2 - Self-critique and cross-agent verification before answering (Priority: P1)

*(User-designated flagship — "subagent discussion".)* Before returning anything to the
principal, the Planner critically evaluates each specialist's output for plausibility,
completeness, and consistency. When it spots a problem, it pushes back — continuing the
conversation with the same specialist, or engaging a verifier — instead of forwarding the
suspect result.

**Why this priority**: This is the capability the principal cares most about; it is what turns
a relay into a thinking system. It also directly protects against the fabricated/incorrect
output the framework exists to prevent.

**Independent Test**: Feed the Planner a specialist result with a deliberately injected error
(e.g. an internally inconsistent figure). Verify the Planner challenges it and seeks
correction/verification before producing a final answer.

**Acceptance Scenarios**:

1. **Given** a specialist result that is internally inconsistent or implausible, **When** the
   Planner reviews it, **Then** the Planner does not deliver it as-is; it re-engages a
   specialist to resolve the issue.
2. **Given** a re-engagement with the *same* specialist, **When** the Planner asks a
   follow-up, **Then** that specialist responds with its prior context intact (a continuing
   thread, not a cold restart).
3. **Given** a factual claim that needs independent confirmation, **When** the Planner is
   uncertain, **Then** it can route the claim to a verifier specialist and reconcile the two.
4. **Given** repeated disagreement, **When** a critique-round bound is reached, **Then** the
   system delivers a best-effort answer that explicitly flags the unresolved uncertainty.

---

### User Story 3 - Per-agent model assignment (Priority: P2)

The operator assigns a different LLM to each agent independently — a low-cost model for
routine work (e.g. web search) and a high-capability model for the Planner's reasoning — and
they all participate in the same run.

**Why this priority**: An enabler that multiplies the value of P1/P2 (a capable Planner is
what makes decomposition and critique work) while controlling cost. Largely a configuration
capability, demonstrable on its own.

**Independent Test**: Configure two agents with two different models/providers, run one
request, and confirm from the run record that each agent invoked its assigned model.

**Acceptance Scenarios**:

1. **Given** distinct model assignments per agent, **When** a run executes, **Then** each
   agent uses exactly its assigned model/provider.
2. **Given** mixed providers in one roster, **When** a run executes, **Then** agents on
   different providers operate together without interfering.

---

### User Story 4 - Ask the principal mid-task, then resume (Priority: P3)

When a request is genuinely ambiguous or a high-stakes decision is needed, the Planner pauses,
asks the principal a clarifying question, and — once answered — continues the **same** task
using everything already gathered, rather than treating the answer as a brand-new request.

**Why this priority**: High value for "team collaboration" feel, but the deepest change
(resumable in-flight work) and dependent on P1 being in place. Sequenced last.

**Independent Test**: Submit an ambiguous request. Verify the Planner asks one focused
question, and after a one-line answer completes the original task without the principal
re-stating it.

**Acceptance Scenarios**:

1. **Given** an ambiguous request, **When** the Planner cannot safely proceed, **Then** it
   asks the principal a clarifying question and the run enters an explicit "awaiting input"
   state rather than ending.
2. **Given** the principal answers, **When** the run resumes, **Then** the Planner continues
   from where it paused, retaining prior context and partial results.
3. **Given** the principal answers, **When** the Planner replies, **Then** the system
   distinguishes "this was a question (task continues)" from "this is the final answer (task
   ends)".

---

### Edge Cases

- A specialist's web search returns nothing or fails → the Planner reports the gap or
  re-routes; no fabricated numbers, quotes, or citations.
- Decomposition explodes into too many sub-tasks → the number of sub-tasks and dispatch rounds
  is bounded.
- Critique loop oscillates without converging → bounded rounds, then a caveated answer.
- Two specialists return conflicting facts → the Planner reconciles or surfaces the conflict
  explicitly rather than silently picking one.
- The principal answers a mid-task question off-topic, or cancels → the Planner handles
  cancel/abort and does not loop.
- An agent's assigned model/provider is unreachable → graceful degradation with a clear error,
  not a silent stall or a fabricated result.
- The Planner is tempted to do the work itself → it must still delegate; it never executes
  domain work directly.

## Requirements *(mandatory)*

### Functional Requirements

**Decomposition & routing**

- **FR-001**: For any non-trivial request, the Planner MUST produce an explicit, inspectable
  decomposition (a set of sub-tasks with their dependencies) before dispatching work.
- **FR-002**: The Planner MUST route each sub-task to the specialist whose declared expertise
  best fits it, and MUST NOT default all work to a single specialist.
- **FR-003**: The system MUST execute independent sub-tasks concurrently and dependent
  sub-tasks in dependency order.
- **FR-004**: The Planner MUST pass each specialist a task instruction rich enough to act on
  (scope, required data points, expected output shape) — not only a bare one-liner.
- **FR-005**: The Planner MUST synthesize specialist results into one structured deliverable
  that addresses every part of the original request.
- **FR-006**: For simple conversational messages, the Planner MUST answer directly without
  decomposition or dispatch.

**Critique & verification (flagship)**

- **FR-007**: Before delivering to the principal, the Planner MUST critically evaluate each
  specialist output for plausibility, completeness, and internal/cross-source consistency.
- **FR-008**: When the Planner identifies a problem, it MUST be able to re-engage the same
  specialist as a continuing thread (prior context retained) rather than a cold restart.
- **FR-009**: The Planner MUST be able to route a claim to a verifier specialist and reconcile
  the verifier's finding with the original result.
- **FR-010**: The system MUST bound critique/verification to at most **2 rounds per request**
  and, when the bound is reached, deliver a best-effort answer that explicitly flags
  unresolved uncertainty.
- **FR-011**: Critique MUST be two-layered: the Planner self-triages every specialist result,
  and for factual claims needing independent confirmation it MUST escalate to a dedicated
  fact-checking/QA (or reviewer) specialist for verification.

**Per-agent models**

- **FR-012**: The operator MUST be able to assign a distinct model and provider to each agent
  independently.
- **FR-013**: Agents using different providers MUST be able to participate in the same run
  simultaneously.

**Mid-task clarification**

- **FR-014**: The Planner MUST be able to pause and ask the principal a clarifying question
  mid-task when the request is genuinely ambiguous or a high-stakes branch needs a decision.
- **FR-015**: After the principal answers, the system MUST resume the same in-flight task using
  accumulated context and partial results — not restart it as a new request.
- **FR-016**: The system MUST distinguish a clarifying question (task continues, run in
  "awaiting input" state) from a final answer (task ends).
- **FR-016a**: Resume MUST be a true suspend/resume of in-flight orchestration: the Planner may
  pause **at any point, including mid-fan-out**, ask the principal, and on answer resume the
  same orchestration with all partial results intact. The run is therefore a resumable state
  machine, not a one-shot request/response.

**Explainability**

- **FR-017**: The system MUST emit an inspectable event for every orchestration step —
  decomposition produced, sub-task dispatched, specialist result, critique/pushback, question
  to principal, principal answer, final synthesis.
- **FR-018**: The UI MUST show, per run, which agent and which model handled each step, and the
  relationships between steps (the dispatch/critique structure), so an observer can reconstruct
  what the team did and why.

**Non-execution principle**

- **FR-019**: The Planner MUST NOT perform domain work itself; all execution is delegated to
  specialists.

### Key Entities

- **Principal request**: the goal the human gives the Planner; the unit a run serves.
- **Plan / decomposition**: the set of sub-tasks for one request, with dependencies marking
  which may run in parallel vs in order.
- **Sub-task**: one unit of work assigned to exactly one specialist role, with a rich
  instruction and expected output shape.
- **Specialist agent**: a role with declared expertise, an assigned model/provider, and tools;
  executes sub-tasks and can carry a continuing thread within a run.
- **Specialist result**: a specialist's structured output, with sources where applicable.
- **Critique / verification round**: a Planner-initiated re-engagement (same specialist or a
  verifier) to challenge or confirm a result before delivery.
- **Clarification exchange**: a Planner question to the principal and the principal's answer,
  with the run paused in between.
- **Run**: one conversation; holds accumulated context and the resumable state of in-flight
  work.
- **Orchestration event**: the inspectable record of each step, consumed by the UI.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a multi-part request (the NASDAQ 10/30/200-day example), the deliverable
  contains a distinct, specialist-sourced section for each requested part — versus today's
  single undifferentiated summary.
- **SC-002**: For a request whose sub-tasks are independent, wall-clock time approximates the
  slowest single branch, not the sum of all branches.
- **SC-003**: Given specialist outputs with an injected error in a controlled test set, the
  Planner detects and challenges the error before delivering in **≥ 80%** of trials.
- **SC-004**: Given an ambiguous request, the Planner asks one clarifying question and, after a
  one-line answer, completes the original task without the principal restating it.
- **SC-005**: From the UI alone, an observer can correctly reconstruct which agent/model did
  what, and the order/relationship of steps, for a target share of runs.
- **SC-006**: An operator can run one request in which at least two agents use two different
  models, confirmed from the run record.

## Assumptions

- The current runtime is the baseline: a single active run, a Planner plus specialist
  sub-agents, web search wired to the searcher roles, and an event bus + dashboard for
  observation already exist.
- Per-agent provider/model configuration already exists at the config layer; broadening the set
  of supported providers is an implementation (plan-level) concern, not a spec change.
- A model capable of genuine multi-step planning is available to the operator for the Planner
  role; weak/tiny models are out of scope as the Planner brain.
- Specialists already retain their conversation history within a run, enabling continuing
  threads for critique.

## Out of Scope (this spec)

- Multiple concurrent runs / multi-tenant operation.
- Persistent specialist memory across runs (threads reset when a conversation is reopened).
- Changes to the destructive-action approval gate beyond what critique/clarification require.
- The specific choice of vendor models (Opus, grok-mini, etc.) — that is a configuration/plan
  decision, not a spec requirement.

## Next Steps (Spec Kit workflow)

1. ~~`/speckit-clarify`~~ — done (see Clarifications, 2026-06-26).
2. `/speckit-plan` — map each requirement to the runtime (orchestrator loop, providers, bus
   events, dashboard); design the resumable-run state machine (FR-016a) and the
   decompose → fan-out → critique → synthesize loop.
3. `/speckit-tasks` — break the plan into ordered, independently-shippable tasks (P1 → P3).
