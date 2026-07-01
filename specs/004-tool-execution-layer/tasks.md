---
description: "Task list — Real Tool Execution Layer (Coder & E2E)"
---

# Tasks: Real Tool Execution Layer (Coder & E2E)

**Input**: Design documents in `specs/004-tool-execution-layer/`
([spec.md](./spec.md), [plan.md](./plan.md))

**Gate**: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) v1.0.0 — passed
in plan.md.

**Tests**: The plan calls for unit tests on the *pure* pieces only — the boundary classifier +
worktree path resolver, the `READ:`/`EDIT:`/`EXEC:` directive parser, the diff summarizer, and the
frontend `parseUnifiedDiff`. These run without a live model, network, or subprocess. Executor /
worktree / subprocess behavior is exercised with a throwaway local git-repo fixture plus manual
runs; model-dependent behavior is verified manually / via the research harness.

## Format: `[ID] [P?] [Story] Description`

- **[P]** = parallelizable (different files, no dependency on another unchecked task).
- **[Story]** = US1 (Coder makes a real change) · US2 (safety boundary + approval gate) ·
  US3 (observable + diff UI) · US4 (E2E Playwright).
- Paths are relative to repo root; runtime code is under `runtime/roster/`, frontend under
  `frontend/src/`.

---

## Phase 1: Setup

- [x] T001 [P] Test fixtures: a throwaway git-repo builder in `runtime/tests/` (init a repo, seed a
  file, set a base branch) for worktree/executor tests; reuse the existing pytest setup from spec
  001 — no new dev dependency. `tests/conftest.py` → `git_repo` fixture + `init_git_repo()`.
- [x] T002 [P] Backend event-contract source: extend `runtime/roster/events.py` with kind constants
  and payload docstrings for `tool.file`, `tool.exec`, `approval.requested`, `approval.resolved`
  (mirrors spec 001's events module) — mirrored by the frontend contract in T007.

---

## Phase 2: Foundational (blocking prerequisites)

**⚠️ No user-story phase begins until this is complete.**

- [x] T003 `runtime/roster/boundary.py` — NEW, pure (no I/O beyond `realpath`): `classify_action()`
  → `(tier, allowed_inside_sandbox, reason)` encoding the allowlist (writes ⊆ worktree), the T3+
  list (network egress, `git push`, `sudo`, out-of-tree delete), and up-tier-when-uncertain; and
  `resolve_in_worktree(path, root)` that rejects `../`, absolute, and symlink-escape paths.
- [x] T004 [P] Tool-directive parser: extend `runtime/roster/protocol.py` to parse a subagent
  reply's trailing directive into `ToolCall { kind: read|edit|exec, path?, body?, command? }`,
  supporting the `EDIT:` fenced-body form; a malformed directive returns a structured rejection.
  Pure.
- [x] T005 [P] `runtime/roster/diffutil.py` — NEW, pure: `summarize_diff(patch)` → per-file
  `[{ path, status, additions, deletions }]` from unified `git diff` text (for the `tool.file`
  `diff` payload and the frontend). No I/O.
- [x] T006 [P] Event emit helpers in `events.py`: thin **bus-only** wrappers (`emit_tool_file`,
  `emit_tool_exec`, `emit_approval_requested`, `emit_approval_resolved`), each dropping unset
  fields; append-only provenance is emitted at the call site that holds `prov` (the orchestrator
  pattern), wired in US1/US2 + T031.
- [x] T007 [P] Frontend contract: add `ToolFileEvent`, `ToolExecEvent`, `ApprovalRequestedEvent`,
  `ApprovalResolvedEvent` to `frontend/src/types/events.ts` (+ `KNOWN_KINDS`, `RosterEvent` union),
  and `file`/`exec`/`diff`/`approval` `TraceItem` kinds + `ActivityCategory` additions to
  `frontend/src/types/models.ts`. Keep in lockstep with T002/T006. (`TraceTimeline` `Line` extended
  to keep `tsc` green; rich diff/exec/approval cards land in T025.)
- [x] T008 [P] Unit tests in `runtime/tests/`: boundary classifier + resolver (inside/outside,
  T-tiers, adversarial `../`/absolute/symlink — T003) ✅ `test_boundary.py` (26 cases); directive
  parser (read/edit/exec/malformed — T004) ✅ `test_protocol.py` (+11 cases); diff summarizer
  (add/modify/delete/rename — T005) ✅ `test_diffutil.py` (7 cases). Full suite: 60 passed.

**Checkpoint**: safety + parsing primitives exist and are unit-tested — no model, network, or
subprocess required.

---

## Phase 3: User Story 1 — The Coder makes a real, verifiable change (Priority: P1) 🎯

**Goal**: The Coder reads/edits real files on an isolated worktree and returns a diff-backed
`TaskResult`.

**Independent Test**: Point Roster at a small target repo, ask for a concrete change; verify from
the worktree/diff (not the Coder's prose) that the change exists on disk and the reported build/test
command actually ran (SC-001).

- [x] T009 [US1] `runtime/roster/workspace.py` — NEW: `WorkspaceManager` — create/reuse/cleanly
  recreate the per-run worktree on `feat/<runId>-<task-slug>`; refuse a dirty or non-git base;
  never write to `main`; cleanup on run end. Uses the T003 resolver (`Worktree.resolve`) for path
  confinement. `test_workspace.py` (9 cases, real git).
- [x] T010 [US1] `runtime/roster/tools.py` — NEW: `ToolExecutor.read/edit/exec` against the
  worktree; `edit` writes then runs a file-scoped `git diff` (via `diffutil`); `exec` runs a
  subprocess. Returns a structured `ToolResult` (`ok`/`error`/`denied`/`gated`) with an
  `as_feedback()` for the loop. `test_tools.py` (13 cases, real git+subprocess). Establishes the
  safe seams that de-risk US2: reads/writes are worktree-confined (T3 resolver → `denied`), exec is
  classified (`classify_action` → boundary/T3+ come back `gated`, not run) and bounded (timeout,
  closed stdin, output cap) — so T016/T017 are largely landed early; T018's ActionProposal+suspend
  and process-group kill remain for US2.
- [x] T011 [US1] Generalize the tool loop in `agent.py`: extend `_run_turn` / directive parsing
  from search-only to `READ:`/`EDIT:`/`EXEC:` (reuse the parse→act→feed-back loop; feed results back
  prefixed `[read]`/`[edit]`/`[exec]`), with a per-turn tool-call budget mirroring
  `MAX_SEARCHES_PER_TURN`; attach the executor only when the agent holds the capability.
  `test_agent_tool_loop.py` (6 cases). Emits `tool.file`/`tool.exec` bus events + a `working`
  status (de-risks T021's backend emission); the executor runs off-loop via `asyncio.to_thread`.
- [x] T012 [US1] `orchestrator.py`: replace `_SUBAGENT_HEAD`'s "what you WOULD do" text with the
  tool-protocol section; build the executor per capability grant (`read:repo`/`write:repo:branch`/
  `run:build`); an out-of-grant action returns `blocked_on_dependency` (no silent widening).
  `wants_file_tools` gates who gets an executor; a per-run worktree is created in `Run.__init__`
  (dirty/non-git target → tools disabled, no fabrication). `test_subagent_prompt.py` (4) +
  `test_orchestrator_tools.py` (2, real `Run`).
- [~] T013 [US1] Target-repo config: `config.py` + `config_api.py` operator-designated target-repo
  path; absent/invalid → execution tools unavailable and the agent says so plainly (no fabrication).
  `config.py` `WorkspaceConfig` (target_repo/worktrees_root, env-overridable) + loading +
  `agents.config.example.yaml` `workspace:` block landed with T012; `config_api.py` Setup
  endpoint + validation still to do.
- [x] T014 [US1] Coder returns a `TaskResult` (validates `task-result.schema.json`) with the
  end-of-task full diff written to `runs/<runId>/artifacts/<taskId>/diff.patch` as a `kind:"diff"`
  artifact. `tools.py` `full_diff()` (cumulative vs base) + `task_result.py` (build/write) wired into
  `_run_dispatch._finalize_tool_result`; emits the final diff event + `task.result.artifact`
  provenance. `test_task_result.py` (4, jsonschema-validated); `jsonschema` added as a dev dep.
- [x] T015 [P] [US1] Test (fake provider + git fixture): an `EDIT` task produces the change on disk
  and a diff artifact; a `READ` returns real contents; the reported `EXEC` exit code matches actual.
  `test_us1_e2e.py` drives a full `Run` (scripted planner→coder) and verifies from disk — worktree
  file + `diff.patch` + jsonschema-valid `TaskResult` — plus the fed-back read contents/exec exit
  (SC-001, SC-004). Shared `runtime_config` fixture added to `conftest.py`.

**Checkpoint**: SC-001 (diff on disk contains the change) + SC-004 (zero fabricated outputs).

---

## Phase 4: User Story 2 — Safe by construction: bounded workspace + boundary gate (Priority: P1)

**Goal**: Every write/command is confined to the worktree; boundary/T3+ actions are blocked and
gated for human approval *before* execution.

**Independent Test**: A task instructing a boundary-crossing action (`git push`, `curl` an external
URL, delete outside the workspace) is blocked, surfaced for approval, and runs only after explicit
approval — never silently (SC-002).

- [ ] T016 [US2] Wire `classify_action` (T003) into `ToolExecutor`: inside-worktree + T0–T2 →
  auto-run and log; out-of-tree read/write or T3+ → do not execute, raise the gate (deny with a
  clear reason, no partial write).
- [ ] T017 [US2] Bounded exec in `tools.py`: per-command timeout (kill the process group),
  captured-output byte cap with a truncation marker, and closed stdin / no TTY. (SC-006)
- [ ] T018 [US2] Boundary gate: emit an `ActionProposal` (validates `action-proposal.schema.json`)
  plus an `approval.requested` event, and suspend via `run_state` `AWAITING_INPUT` (reuse spec 001 —
  no new state machine); record the risk classification to provenance.
- [ ] T019 [US2] Approve/reject resume in `server.py`: reuse `/api/chat` awaiting-input routing
  (optional sugar: `POST /api/approvals/{propId}`); approve → execute + `approval.resolved(approved)`;
  reject → abandon and tell the agent to proceed without it (the run does not re-propose / loop).
- [ ] T020 [P] [US2] Tests: classifier-in-executor denies an out-of-tree write (no partial write);
  a boundary command suspends (`awaiting_input`); approve executes / reject abandons; a `sleep`/`yes`
  command is terminated within the timeout and its output truncated.

**Checkpoint**: SC-002 (100% of boundary actions gated) + SC-006 (runaways terminated).
**MVP = Phase 3 + Phase 4** — a Coder that edits real files on an isolated branch, safely gated.

---

## Phase 5: User Story 3 — Every tool action is observable + the diff view (Priority: P2)

**Goal**: The dashboard shows each read/write/exec (path, exit code, truncated output), the diff,
and each approval — at search-tool parity. *This is the "show me what changed" payoff.*

**Independent Test**: From the UI alone, enumerate every command the Coder ran with its exit code
and open the produced diff (SC-003).

- [ ] T021 [US3] Emit through the executor + gate: `tool.file` (read/write/diff), `tool.exec`
  (command/output), and `approval.*` — each an append-only provenance event **and** a live bus event
  (constitution V), using the T006 helpers.
- [ ] T022 [US3] `frontend/src/store/handleEvent.ts` reducers for the new events —
  `activityFromDiff`/`activityFromExec`, progress-trace pushes at search parity, and set
  awaiting-input on `approval.requested`.
- [ ] T023 [P] [US3] `frontend/src/components/diff/lib/parseUnifiedDiff.ts` — NEW pure parser
  (unified patch → `files → hunks → lines` with old/new line numbers) + a Vitest test.
- [ ] T024 [US3] `frontend/src/components/diff/DiffView.tsx` + `diff.module.css` — NEW VS Code-style
  per-file renderer (path + status badge, `+adds/−dels`, line-number gutters, `+`/`−`/context
  coloring, collapsible; oversized/binary → one-line summary + raw-patch fallback). Depends on T023.
- [ ] T025 [US3] Wire into surfaces: `DiffCard`/`ExecCard`/`ApprovalCard` in
  `components/orchestration/TraceTimeline.tsx` (live + collapsible per-answer record) and diff/exec
  rendering in `components/activity/ActivityPanel.tsx`, mirroring the search-results rendering.
- [ ] T026 [US3] Approval affordance: reuse the awaiting-input UI (spec 001/002) with approve/reject
  actions that call the T019 endpoint.

**Checkpoint**: SC-003 — reconstruct every command + exit code and open the diff from the UI alone.

---

## Phase 6: User Story 4 — E2E verification via Playwright (Priority: P3)

**Goal**: The E2E agent runs a named suite via `playwright-cli` against a running build, read-only,
returning structured pass/fail + an HTML report.

**Independent Test**: With a change landed and a build up, run a smoke suite; the reported pass/fail
matches the app's real behavior, with an HTML report artifact produced (SC-005).

- [ ] T027 [US4] E2E runner: an `EXEC:`-based `playwright-cli` invocation (reusing `ToolExecutor`
  bounds) wired to the E2E agent's grant; produces `runs/<runId>/artifacts/<taskId>/e2e-report/`.
- [ ] T028 [US4] Read-only guard: the E2E agent MUST NOT edit `e2e-agent/e2e-test/test-definitions/**`;
  a contradicting test surfaces as a failure (no silent edit); a missing build → report the missing
  prerequisite (no fabricated run).
- [ ] T029 [US4] E2E prompt/runner wiring in `orchestrator.py` + the `e2e.agent.md` runtime section;
  structured pass/fail with snapshot-cited evidence in the `TaskResult`.

**Checkpoint**: SC-005 — reported pass/fail matches real app behavior.

---

## Phase 7: Polish & cross-cutting

- [ ] T030 [P] Docs: `runtime/README.md` + `runtime/agents.config.example.yaml` (target-repo path,
  tool grants, timeout/output/diff caps); document the worktree isolation model and its trust
  assumption.
- [ ] T031 [P] Provenance completeness: every tool action + approval lands in
  `runs/<id>/provenance.jsonl` (constitution V).
- [ ] T032 [P] Tune defaults: per-command timeout, captured-output byte cap, diff size cap, and the
  per-turn tool-call budget.
- [ ] T033 Setup page (spec 003): expose the target-repo path field in the setup UI if present.

---

## Dependencies & Execution Order

- **Setup (T001–T002)**: no deps; parallel.
- **Foundational (T003–T008)**: depends on Setup; **blocks all user stories**. Pure pieces
  (T003–T005, T007) before their tests (T008); T006/T007 parallel.
- **US1 (T009–T015)**: depends on Foundational. T009 (workspace) + T010 (executor) before T011
  (loop) before T012 (prompt/grant wiring); T013 config parallel; T014 after the executor; T015
  after the loop.
- **US2 (T016–T020)**: depends on US1 (the gate wraps the executor) + the T003 classifier.
  T016/T017 before T018/T019; T020 after.
- **US3 (T021–T026)**: backend T021 depends on US1/US2 producing actions. The **frontend** (T022–T026)
  can be built against the typed contract from T007 in parallel once Foundational lands; end-to-end
  verification needs US1/US2. T023 (parser) before T024 (DiffView); T021 before T025/T026.
- **US4 (T027–T029)**: depends on US1 (executor) + US2 (bounds). Can follow US3 or proceed in
  parallel if staffed.
- **Polish (T030–T033)**: after the relevant stories; T033 coordinates with spec 003.

### Within each story

- Pure helpers (classifier, resolver, parser, summarizer) and their unit tests before the I/O
  wiring that uses them.
- The executor + worktree (US1) before the boundary gate (US2) before observability (US3).
- A story's checkpoint (its SC) is met before moving to the next priority.
- **MVP = Phase 3 (US1) + Phase 4 (US2)**: a Coder that edits real files on an isolated branch,
  safely gated. US3 is the immediately-following legibility payoff — the VS Code-style diff view the
  feature is really about; US4 adds E2E verification.
