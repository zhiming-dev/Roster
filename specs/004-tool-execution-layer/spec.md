# Feature Specification: Real Tool Execution Layer (Coder & E2E)

**Feature Branch**: `004-tool-execution-layer`

**Created**: 2026-07-01

**Status**: Draft

**Constitution**: v1.0.0

**Input**: User description: "Give the specialists a real tool-execution layer so they can *do*
work, not just describe it. Start with the Coder — real file read/write plus shell execution in
a sandbox — then wire the E2E agent's Playwright runner. Today every specialist except the web
searcher is a talking head: `coder`, `e2e`, `reviewer`, `qa` have rich personas and runner
SKILLs, but the runtime never executes any of them; the only real tool is web search. This is the
single biggest gap between Roster and an agent that actually changes the world."

## Context & Problem

Roster's orchestration is real: the Planner decomposes, fans out in parallel, critiques, and can
pause to ask the principal (spec 001). Its explainability UI is real (spec 002). But the agents
cannot *act*. The only tool wired into the runtime is web search
([`runtime/roster/search.py`](../../runtime/roster/search.py), invoked via the `SEARCH:` loop in
[`runtime/roster/agent.py`](../../runtime/roster/agent.py)). The Coder cannot read or write a
file; the E2E agent cannot open a browser; skills are injected into the system prompt as *text*,
never executed. The subagent system prompt even admits it, instructing specialists to describe
"what they WOULD do" ([`runtime/roster/orchestrator.py`](../../runtime/roster/orchestrator.py)).

The design assets for a doing-system already exist and are unused: `coder.agent.md`
(`tools: [read, edit, execute, search]`, feature-branch-only, T2-max), the `coder-runner` and
`e2e-runner` SKILLs (branch strategy, diff/report artifacts, `task-result.schema.json`), and the
`approval-gate` SKILL (T0–T4 risk tiers and gate policy). This feature makes the runtime **execute
real tools** — closing the "会说 → 会做" gap — while honoring the constitution's non-negotiables:
human-in-the-loop for irreversible actions (I), safety/recoverability over speed (II), least
privilege (III), no fabrication (IV), and everything observable (V).

## Clarifications

### Session 2026-07-01

- Q: How are the Coder's shell/file-write tools isolated? → A: **git worktree + subprocess.** Each
  run gets a dedicated git worktree on a feature branch of the operator's target repository;
  file/shell tools run as subprocesses with that worktree as their working directory. Safety comes
  from a path allowlist (writes confined to the worktree), branch isolation (never `main`), and the
  approval gate at the sandbox boundary. Full container/VM isolation is deferred hardening, not v1.
  (Resolves FR-001, FR-011.)
- Q: What code does the Coder work on (workspace source)? → A: **An operator-designated target
  repository.** Roster acts as a development agent over an *external* codebase the operator points
  it at (in Setup / config), like Hermes/OpenClaw. A fresh-scratch-workspace mode (no pre-existing
  repo) is out of scope for this spec. (Resolves FR-003.)
- Q: How much approval friction in v1? → A: **Auto inside the sandbox, hard gate at the boundary.**
  Reads, writes, and non-destructive shell *inside the run's worktree* (T0–T2) run automatically
  and are logged. Anything that crosses the boundary — network egress, `git push`, deleting files
  outside the worktree, privilege escalation, or any T3+ action — is **blocked and surfaced for
  explicit human approval before execution**, per constitution principle I. (Resolves FR-012,
  FR-013.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The Coder makes a real, verifiable code change (Priority: P1)

The Planner dispatches a concrete coding sub-task to the Coder ("add an input-validation helper to
`utils.py` and a unit test for it"). The Coder reads the relevant existing files, edits/creates
files on an isolated feature-branch worktree of the target repo, runs a build/test command to check
its work, and returns a structured result with a real diff — not a description of a diff.

**Why this priority**: This is the entire point of the feature and the single most valuable jump
in the product — from a system that *talks about* work to one that *does* it. Everything else
(safety boundary, observability, E2E) exists to make this capability trustworthy and legible.

**Independent Test**: Point Roster at a small target repo. Ask for a specific, checkable change.
Verify by inspecting the worktree/diff (not the Coder's prose) that the change actually exists on
disk and the reported build/test command actually ran.

**Acceptance Scenarios**:

1. **Given** a target repo and a concrete coding task, **When** the Coder works, **Then** it reads
   real file contents from the workspace (not invented ones) before editing.
2. **Given** an edit task, **When** the Coder completes it, **Then** the described file changes are
   actually present on disk in the run's worktree and captured as a diff artifact.
3. **Given** a task with a build/test step, **When** the Coder runs it, **Then** the runtime
   executes the real command and the Coder's reported outcome matches the actual exit code/output.
4. **Given** the Coder finishes, **When** it reports back to the Planner, **Then** it returns a
   structured `TaskResult` (`success` / `partial` / `failure`) with the diff and the commands run.

---

### User Story 2 - Safe by construction: bounded workspace + boundary approval gate (Priority: P1)

Every file write and command the Coder issues is confined to the run's worktree. Any action that
would escape that sandbox — write outside the worktree, reach the network, `git push`, `sudo`,
delete outside the workspace, or anything classified T3+ — is blocked and surfaced to the principal
as a human-approval request *before* it can run. The runtime never silently executes a
boundary-crossing action.

**Why this priority**: Non-negotiable per the constitution (I: human-in-the-loop; II: safety over
speed; III: least privilege). It is inseparable from US1 — you cannot responsibly let an agent run
shell without the boundary. Ships alongside US1, not after.

**Independent Test**: Give the Coder a task whose instructions include a boundary-crossing action
(e.g. "then `git push` to origin" or "curl an external URL"). Verify the runtime blocks it, surfaces
a human-reviewable approval request, and executes it only after explicit approval — never silently.

**Acceptance Scenarios**:

1. **Given** a write targeting a path outside the run's worktree, **When** the Coder attempts it,
   **Then** the runtime denies it and reports the denial (no fabrication, no partial write).
2. **Given** a command that crosses the boundary (network egress, `git push`, `sudo`, delete
   outside workspace, or T3+), **When** the Coder attempts it, **Then** the runtime blocks execution
   and surfaces a short, human-reviewable approval request; the run enters an "awaiting input" state.
3. **Given** a blocked action, **When** the principal approves it, **Then** the runtime executes it
   and records the approval; **When** the principal rejects it, **Then** the action is abandoned and
   the Coder is told to proceed without it.
4. **Given** reads/writes/non-destructive shell *inside* the worktree, **When** the Coder issues
   them, **Then** they run automatically (no prompt) and are logged.
5. **Given** a long-running or interactive command, **When** it exceeds the configured timeout or
   waits on a TTY, **Then** the runtime terminates it and reports the timeout rather than hanging.

---

### User Story 3 - Every tool action is observable (Priority: P2)

The dashboard shows what the specialists actually did: each file read/written (with path), each
command (with exit code and truncated output), each build/test result, the resulting diff, and any
approval requested/granted/rejected — rendered in the run trace with the same legibility as today's
web-search steps, and viewable after the fact.

**Why this priority**: Explainability by construction is a constitution principle (V) and the
product's identity. Real actions that a human cannot inspect are worse than no actions. Depends on
US1/US2 producing the actions to render.

**Independent Test**: Run a Coder task, then from the UI alone reconstruct which files changed,
which commands ran and their exit codes, and open the produced diff — without reading server logs.

**Acceptance Scenarios**:

1. **Given** a Coder run, **When** it edits files and runs commands, **Then** each action emits an
   append-only provenance event and a live bus event.
2. **Given** the live run, **When** the Coder acts, **Then** the trace timeline shows each tool step
   (parity with the existing search-tool rendering), including command exit status.
3. **Given** a completed run, **When** the observer opens it, **Then** they can view the produced
   diff and the captured command output attached to the run record.

---

### User Story 4 - E2E verification via Playwright (Priority: P3)

After the Coder lands a change and a build is running, the Planner dispatches the E2E agent, which
drives a real browser through a named test suite via `playwright-cli`, evaluates pass/fail from page
snapshots, and returns a structured result with an HTML report. It is read-only against the app and
never edits test definitions to force a pass.

**Why this priority**: The second tool integration and explicitly sequenced after the Coder ("先
coder … 再 e2e"). It is dependent on US1 landing changes and a build being available, and reuses the
US1–US3 execution + observability substrate, so it is sequenced last.

**Independent Test**: With a change landed and a build up, ask the Planner to run a smoke suite.
Verify the E2E agent actually launches a browser, runs the suite, and its reported pass/fail matches
the app's real behavior, with an HTML report artifact produced.

**Acceptance Scenarios**:

1. **Given** a running build and a named suite, **When** the E2E agent is dispatched, **Then** it
   executes the suite via `playwright-cli` against the real app and returns structured pass/fail.
2. **Given** a test whose definition looks wrong, **When** the app's behavior contradicts it,
   **Then** the E2E agent lets the test fail and surfaces the discrepancy — it does NOT edit the
   test definition to pass.
3. **Given** a completed suite, **When** it reports back, **Then** it produces an HTML report
   artifact and cites snapshot evidence for each pass/fail.
4. **Given** no build is available, **When** the E2E agent is dispatched, **Then** it reports the
   missing prerequisite instead of fabricating a run.

---

### Edge Cases

- The operator has not designated a target repo → execution tools are unavailable; the agent says
  so plainly and does not fabricate file contents or command output.
- The target path is not a git repo, or `main` is dirty → the runtime reports the setup problem
  rather than writing into an inconsistent tree.
- A command hangs, loops, or waits for interactive input → bounded timeout + non-TTY; the runtime
  terminates and reports it.
- A command produces enormous output → output is captured up to a bounded size and truncated with a
  clear marker; the run does not OOM.
- The Coder's requested action needs a capability outside its grant → it returns
  `blocked_on_dependency`; the runtime never silently widens the grant.
- The Coder tries to edit a read-only zone (test fixtures, `main`, paths outside the worktree) →
  denied; the failing signal is surfaced, not worked around.
- A worktree/branch from a previous run already exists → the runtime reuses or cleanly recreates it;
  it never clobbers unrelated branches.
- The principal rejects a boundary action mid-task → the Coder continues without it (or reports it
  cannot complete), and the run does not loop.
- The model emits a malformed tool call → the runtime rejects it with a corrective message rather
  than executing an ambiguous command.

## Requirements *(mandatory)*

### Functional Requirements

**Execution substrate & workspace**

- **FR-001**: The runtime MUST provide agents granted execution tools with a sandboxed workspace: a
  git worktree on a dedicated feature branch of the operator-designated target repository, created
  per run and isolated from the target repo's primary working tree.
- **FR-002**: File and shell tools MUST use the run's worktree as their working directory; all
  relative paths resolve inside it.
- **FR-003**: The operator MUST be able to designate the target repository path (config / Setup).
  Absent a valid target repo, execution tools MUST be unavailable and the agent MUST say so rather
  than fabricate results.
- **FR-004**: Worktree/branches MUST follow a stable, run-scoped naming convention
  (`feat/<runId>-<task-slug>`), MUST NOT write to `main`/protected branches, and MUST be cleanly
  reusable/recreatable across runs without clobbering unrelated branches.

**Coder file & shell tools (the capability)**

- **FR-005**: The Coder MUST be able to read files within the workspace, returning real contents.
- **FR-006**: The Coder MUST be able to create, modify, and delete files within the workspace.
- **FR-007**: The Coder MUST be able to run shell commands within the workspace, capturing stdout,
  stderr, and exit code, under a bounded per-command timeout and a bounded captured-output size,
  with no interactive/TTY prompts.
- **FR-008**: The Coder MUST produce a diff artifact of its changes and a structured `TaskResult`
  (`success` / `partial` / `failure`) that validates against `task-result.schema.json`.
- **FR-009**: The Coder MUST NOT fabricate tool output: every claimed file change or command result
  MUST correspond to an actually-executed tool call (constitution IV).
- **FR-010**: Tool invocations MUST be expressed in a form the runtime can deterministically parse
  and execute, extending the existing search-style tool loop to `read` / `edit` / `execute`; a
  malformed invocation MUST be rejected with a corrective message, not guessed at.

**Safety boundary & approval gate (NON-NEGOTIABLE)**

- **FR-011**: File writes and command execution MUST be confined to the run's worktree; any attempt
  to read-modify or execute against paths outside it MUST be denied.
- **FR-012**: Boundary-crossing actions — network egress, `git push`, deleting files outside the
  workspace, privilege escalation (`sudo`), or any action classified T3+ — MUST be blocked and
  surfaced to the principal as a human-reviewable approval request BEFORE execution. The runtime
  MUST NOT bypass the gate (constitution I).
- **FR-013**: Reads, writes, and non-destructive shell inside the worktree (T0–T2) MUST auto-execute
  and be logged; the sandbox boundary is the hard gate (the chosen v1 policy).
- **FR-014**: The runtime MUST classify each proposed action's risk tier per the approval-gate
  policy (T0–T4) and record the classification, up-classifying when uncertain.
- **FR-015**: A blocked action MUST NOT stall silently: the run MUST enter the existing
  "awaiting input" state (reusing spec 001's suspend/resume) with a short, opinionated approval
  summary, resuming on approve and abandoning the action on reject.
- **FR-016**: Command execution MUST be bounded and non-hanging: a per-command timeout terminates
  runaway/looping/interactive commands, and the termination is reported (not silently swallowed).

**Least privilege / capability grants**

- **FR-017**: Each agent's execution capabilities MUST be governed by an explicit capability grant
  (e.g. `read:repo`, `write:repo:branch`, `run:build`). An action outside the grant MUST return
  `blocked_on_dependency`; the grant MUST NOT be silently widened (constitution III).

**E2E Playwright tool**

- **FR-018**: The E2E agent MUST be able to run a named test suite via `playwright-cli` against a
  running build and return a structured pass/fail result with evidence.
- **FR-019**: The E2E agent MUST be read-only against the app and its test definitions; it MUST NOT
  edit test definitions to force a pass, and MUST surface a contradicting test as a failure.
- **FR-020**: The E2E agent MUST produce an HTML report artifact and cite snapshot evidence for each
  pass/fail; if no build is available it MUST report the missing prerequisite, not fabricate a run.

**Observability (explainability parity)**

- **FR-021**: Every tool action — file read/write (path), command (command + exit code + truncated
  output), build/test result, diff produced, and approval requested/granted/rejected — MUST emit an
  append-only provenance event and a live bus event (constitution V).
- **FR-022**: The UI MUST render tool actions in the run trace with parity to the existing
  search-tool explainability (which agent, which action, outcome/exit status), and MUST let an
  observer view the produced diff and captured command output attached to the run record.

### Key Entities

- **Target repository**: the external git repo the operator points Roster at; the source of truth
  the Coder works against.
- **Workspace / worktree**: a per-run git worktree on a feature branch, the sandbox within which all
  file/shell tools operate.
- **Capability grant**: the explicit set of capabilities an agent holds (`read:repo`,
  `write:repo:branch`, `run:build`, …); bounds what its tools may do.
- **Tool call**: a runtime-parseable request from an agent to `read` / `edit` / `execute` (mirroring
  the existing `SEARCH:` mechanism).
- **Tool result**: the actual outcome of a tool call (file contents, command stdout/stderr/exit
  code) fed back to the agent.
- **ActionProposal**: a boundary-crossing action pending human approval, classified by risk tier
  with a reversibility plan (per `action-proposal.schema.json`).
- **Approval decision**: the principal's approve/reject of an ActionProposal, recorded to
  provenance.
- **Diff artifact**: the captured change set produced by a Coder run.
- **TaskResult**: the Coder's structured outcome (`task-result.schema.json`).
- **E2E suite / report**: the named test suite the E2E agent runs and the HTML report it produces.
- **Tool event**: the append-only, UI-consumable record of each tool action and approval.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a concrete coding task against a target repo, the Coder produces a diff that, when
  inspected on disk, actually contains the requested change — verified from the worktree, not the
  Coder's prose — in a high share of controlled trials.
- **SC-002**: For a task instructing a boundary-crossing action (`git push`, `curl` an external URL,
  delete outside the workspace), the action is blocked and surfaced for approval in **100%** of
  trials; none execute without explicit approval.
- **SC-003**: From the UI alone, an observer can enumerate every command the Coder ran with its exit
  code and open the resulting diff, for a target share of runs.
- **SC-004**: In a controlled set, the Coder reports **zero** file changes or command outputs that
  did not actually occur (no-fabrication), checked against the provenance log.
- **SC-005**: After the Coder lands a change and a build is up, the E2E agent runs a suite and its
  reported pass/fail matches the app's real behavior.
- **SC-006**: A runaway/looping/interactive command is terminated within the configured timeout and
  reported, with no hung runs.

## Assumptions

- `git` is available and the operator-designated target is a valid git repository with a usable
  base branch; creating a worktree/feature branch there is acceptable.
- A model capable of genuine multi-step tool use drives the Coder; weak/tiny models are out of scope
  as the Coder brain (consistent with spec 001's Planner assumption).
- The existing suspend/resume state machine (spec 001, `run_state.py`) and event bus + dashboard
  (spec 001/002) are reused for approval pauses and observability — this feature extends them, it
  does not rebuild them.
- `playwright-cli` and a running build are available in the environment when US4 is exercised.
- Single active run remains the baseline (spec 001); one active worktree at a time is sufficient for
  this spec.
- The runtime host is trusted to run subprocesses; worktree confinement + boundary gate are the v1
  isolation model (not a hostile-multi-tenant threat model).

## Out of Scope (this spec)

- Full container/VM/OS-level sandbox isolation — deferred hardening on top of the worktree model.
- Fresh-scratch-workspace mode (building from an empty directory with no target repo).
- Auto-merge to `main`, deploy, or PR creation/commenting — those are T3+ and gated here; their
  orchestration is a later spec.
- Multi-language/framework build auto-detection beyond running operator/agent-provided commands.
- Persistent workspaces or specialist memory across runs (worktrees are per-run).
- A full migration to provider-native structured function-calling — the search-style tool loop is
  extended for v1; a native tool-use protocol is a separate concern.
- Multiple concurrent runs / multi-tenant isolation.
- Wiring the `reviewer` role's execution tools (lint/PR comment) — this spec covers `coder` then
  `e2e`; `reviewer`/`ops` follow later.

## Next Steps (Spec Kit workflow)

1. ~~`/speckit-clarify`~~ — done (see Clarifications, 2026-07-01: isolation = worktree+subprocess;
   workspace = operator-designated target repo; gate = sandbox-auto + boundary hard-gate).
2. `/speckit-plan` — map requirements onto the runtime: the worktree/workspace manager, the
   tool-execution loop extending `agent.py`'s search loop (`read`/`edit`/`execute`), the boundary +
   approval gate reusing `run_state.py` suspend/resume and the `approval-gate` policy, the new bus/
   provenance event kinds, and the dashboard trace/diff/output viewers. Include the Constitution
   Check (esp. I, III, IV, V) and Complexity Tracking for the subprocess trust model.
3. `/speckit-tasks` — break the plan into ordered, independently-shippable tasks (US1 + US2 as the
   P1 increment, then US3 observability, then US4 E2E).
