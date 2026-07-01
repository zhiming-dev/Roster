# Implementation Plan: Real Tool Execution Layer (Coder & E2E)

**Branch**: `004-tool-execution-layer` | **Date**: 2026-07-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-tool-execution-layer/spec.md`

## Summary

Turn the specialists from talking heads into *doers*. Today the only real tool is web search:
[`agent.py`](../../runtime/roster/agent.py) runs a `SEARCH:`-line loop and emits `tool.search`
events; every other specialist is instructed to describe "what they WOULD do"
([`orchestrator.py`](../../runtime/roster/orchestrator.py), `_SUBAGENT_HEAD`). This feature
generalizes that one proven loop into a **tool-execution loop** (`READ:` / `EDIT:` / `EXEC:`) that
runs against a **per-run git worktree** of an operator-designated target repo, confined by a **path
allowlist + boundary approval gate**, and streamed to the dashboard as new tool events — including
a **VS Code-style diff** of exactly what the Coder changed. E2E's Playwright runner reuses the same
substrate (US4). All backend logic lives in `runtime/roster/`; the React UI (spec 002) gains a diff
renderer and tool-step parity with search. The HITL gate, no-fabrication rule, and append-only
provenance are preserved and strengthened.

## Technical Context

**Language/Version**: Python 3.10+ (runtime) + TypeScript/React (dashboard, spec 002).

**Primary Dependencies**: existing — FastAPI, httpx, PyYAML, the in-process `bus`, `LlmQueue`,
`git` on the host. Frontend — existing `react-markdown`/Motion/Zustand only; **no new diff library**
(a small custom unified-diff parser + renderer, matching how the repo hand-rolls the search-results
list). No new Python runtime dependency: the tool loop is text-directive (native function-calling is
out of scope per the spec).

**Storage**: existing SQLite event store ([`store.py`](../../runtime/roster/store.py)) — extended
only with new event *kinds* (JSON blobs, no schema migration). Artifacts (diffs, command logs, E2E
reports) written under `runs/<runId>/artifacts/<taskId>/` per the provenance convention. The target
repo's worktree lives outside `runs/` (it is the operator's code, not run state).

**Testing**: none formal today (JSON validated against `shared/schemas/*.schema.json`). This feature
adds `pytest`-style unit tests for the pure pieces — the tool-directive parser, the boundary
classifier (allowlist + T3+ detection), the diff summarizer, and the worktree path-resolver —
runnable without a live model or network. Frontend adds a `parseUnifiedDiff` unit test (Vitest).

**Target Platform**: local/self-hosted Python service; a trusted host that can create git worktrees
and run subprocesses.

**Project Type**: backend service (the agent runtime) + an event contract consumed by the SPA.

**Performance Goals**: tool calls are bounded — a per-command timeout, a captured-output size cap,
and a per-turn tool-call budget (mirroring `MAX_SEARCHES_PER_TURN`). Per-edit diffs are file-scoped
so they render instantly; the full-change diff is computed once at task end.

**Constraints**: writes/exec confined to the worktree; boundary-crossing or T3+ actions blocked and
gated (constitution I); no fabricated tool output (IV); every tool action emits an event (V); tool
results validate against `task-result.schema.json` (VI).

**Scale/Scope**: one active run, one active worktree (spec 001 baseline). `coder` first, then
`e2e`; `reviewer`/`ops` execution tools are a later spec.

## Constitution Check

*GATE: checked against [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
v1.0.0.*

| Principle | Bearing | Status |
|---|---|---|
| I. Human-in-the-loop | The whole point of the boundary gate: network egress, `git push`, out-of-tree deletes, `sudo`, any T3+ are blocked and surfaced for approval before execution; the runtime never bypasses the gate | ✅ strengthens |
| II. Safety & recoverability | Feature-branch worktree (never `main`), path allowlist, bounded timeouts/output, up-tier when uncertain; every change is a reviewable diff on an isolated branch | ✅ |
| III. Least privilege / restraint | Tools wired only for the capabilities in each agent's grant (`read:repo`, `write:repo:branch`, `run:build`); an out-of-grant action returns `blocked_on_dependency`, never a silent widening; the Planner still executes nothing | ✅ |
| IV. Truth over plausibility | Every claimed file change/command result corresponds to an actually-executed tool call; malformed tool calls are rejected, not guessed; deletes the "what you WOULD do" prompt language | ✅ strengthens |
| V. Everything observable | New append-only + live events for each read/write/exec/diff and each approval requested/granted/rejected; the UI renders them at search-tool parity plus a diff viewer | ✅ strengthens |
| VI. Typed, validated contracts | Coder returns a `TaskResult` validating `task-result.schema.json` (already has `artifacts[].kind:"diff"` + `blocked_on_*`); boundary actions use `action-proposal.schema.json`; new event kinds typed for the SPA | ✅ |

**Engineering-standard note (host trust):** the v1 isolation model is worktree confinement +
boundary gate + subprocess, *not* container/VM isolation (deferred hardening per the spec's Out of
Scope). The host is assumed trusted (not hostile-multi-tenant). This is the one deliberate
simplification — recorded in Complexity Tracking below — and it does not weaken any principle: the
gate still stops every boundary-crossing action.

## Research & Decisions (Phase 0)

| Decision | Choice | Rationale / alternatives |
|---|---|---|
| Tool-call protocol | Extend the proven `SEARCH:`-line loop to `READ: <path>`, `EDIT: <path>` (with a fenced body block on the following lines), and `EXEC: <cmd>`. One tool directive per turn; the runtime runs it and feeds the result back as the next turn, exactly like search. | Reuses `agent.py`'s parse→act→feed-back machinery and the weak-model-friendly text protocol. Native structured function-calling is explicitly deferred (spec Out of Scope) to keep v1 small and provider-agnostic. |
| Isolation | git **worktree on a feature branch** of the operator's target repo + **subprocess** with that worktree as cwd. Safety = path allowlist (writes ⊆ worktree) + branch isolation (never `main`) + boundary gate. | Resolves the spec's clarification. Full container/VM isolation is deferred hardening, not v1. |
| Workspace lifecycle | A `WorkspaceManager` creates `feat/<runId>-<task-slug>` as a worktree per run under a runtime-managed dir; reuses/cleanly recreates on re-run; never clobbers unrelated branches; refuses if the target isn't a clean git repo. | FR-001/002/004 and the "worktree already exists / dirty `main`" edge cases. |
| Boundary classification | A pure `classify_action(tool, target)` returns `(tier, allowed_inside_sandbox)`. Reads/writes/non-destructive shell **inside** the worktree = T0–T2 → auto-run + log. Network egress, `git push`, out-of-tree path, `sudo`, `rm -rf` outside, or any T3+ → block + gate. Up-tier when uncertain. | FR-011–014. The allowlist is the hard line; the classifier is pure and unit-tested. |
| Approval pause | Reuse spec 001's `AWAITING_INPUT` state ([`run_state.py`](../../runtime/roster/run_state.py)). A blocked action emits an `ActionProposal` + `approval.requested`, suspends the run, and resumes on the principal's approve/reject — no new state machine. | FR-012/015; consistent with the existing clarification suspend/resume. |
| Command safety | Subprocess with a per-command timeout, captured-output byte cap (truncate with a marker), no TTY (stdin closed), killed process group on timeout. | FR-007/016 and the hang/loop/huge-output edge cases. |
| **Diff display** | After each `EDIT` (file-scoped) and once at task end (full change set), run `git diff` in the worktree, emit a `tool.file` `diff` event carrying a parsed per-file summary + the unified patch, and write `diff.patch` as a `TaskResult` artifact. The UI renders it **VS Code-style** (per-file, +/− gutters, add/del counts) via a small custom parser; it degrades to a plain unified patch (Copilot-CLI look) when oversized. | Directly answers the P1 "show me what actually changed" ask. No heavy dep; see the dedicated section below. |
| E2E tool | The E2E agent gets an `EXEC:`-based Playwright runner (`playwright-cli` against a running build), read-only, producing an HTML report artifact; reuses the US1–US3 substrate. | FR-018–020; sequenced last per "先 coder … 再 e2e". |
| Schemas | No schema bump needed. `task-result.schema.json` already has `artifacts[].kind` and `blocked_on_*` statuses; `action-proposal.schema.json` covers boundary proposals. Only new *event kinds* are added (additive, typed for the SPA). | Constitution VI; keeps the change surface minimal. |

## Tool-call protocol (Phase 1 — extends the search loop)

The subagent reply protocol grows from one directive to a small, deterministic set. Exactly one
tool directive may appear, as the last line(s) of a reply; the runtime executes it and feeds the
result back as the next turn (prefixed `[read]` / `[exec]` / `[edit]`), then the agent continues or
answers with no directive — identical control flow to `SEARCH:` today.

- `READ: <relative-path>` → returns real file contents (or a clear "not found"), capped in size.
- `EDIT: <relative-path>` followed by a fenced block → writes the file inside the worktree, then
  the runtime replies with the resulting **file-scoped diff**.
- `EXEC: <command>` → runs in the worktree under timeout/output caps; returns stdout/stderr/exit.

A malformed directive (bad path, missing body, unparseable command) is **rejected with a
corrective message**, not guessed at (FR-010). Directives that resolve outside the worktree or are
classified T3+ are **not executed** — they raise the boundary gate (below).

## New event contract (Phase 1 — consumed by the SPA)

Emitted on the existing `bus` (`{kind, ts, ...payload}`), persisted by `store.py`, and typed in
[`events.py`](../../runtime/roster/events.py) as the single source of truth (mirroring the spec 001
event module). Frontend types added to [`events.ts`](../../frontend/src/types/events.ts) +
`KNOWN_KINDS`:

- `tool.file` — `{ agent, phase: "read"|"write"|"diff", path?, bytes?, files?, patch?, truncated? }`
  where the `diff` phase carries `files: [{ path, status, additions, deletions }]` + the unified
  `patch`.
- `tool.exec` — `{ agent, phase: "command"|"output", command, exitCode?, stdout?, stderr?, durationMs?, timedOut?, truncated? }`.
- `approval.requested` — `{ agent, propId, tier, action, summary }` (sets run `awaiting_input`).
- `approval.resolved` — `{ propId, decision: "approved"|"rejected" }`.

No existing event kind changes; unknown kinds are already ignored by `parseEvent` (forward-compatible).

## Boundary & approval gate (Phase 1 — the non-negotiable)

```text
tool directive ─▶ resolve path / parse cmd ─▶ classify_action
   ├─ inside worktree & T0–T2 ─▶ execute ─▶ log tool.* event ─▶ feed result back
   └─ boundary / T3+ ─▶ ActionProposal + approval.requested ─▶ run.AWAITING_INPUT
                         ├─ approve ─▶ execute + approval.resolved(approved)
                         └─ reject  ─▶ abandon; tell agent to proceed without it
```

- The classifier and path-resolver are **pure and unit-tested** (no I/O), so the safety line is
  verifiable without a model.
- The gate reuses the existing suspend/resume: `/api/chat` already routes the next principal message
  as the answer when `awaiting_input`; approve/reject is that answer (a dedicated
  `POST /api/approvals/{propId}` endpoint is optional sugar over the same resume).
- A rejected action never loops the run: the agent is told to continue without it or report it
  cannot complete (FR-015 + the "principal rejects mid-task" edge case).

## Diff display design (the "show me what changed" requirement)

This is the P1 legibility payoff — the Coder shows a real, inspectable diff, not prose about one.

**Backend.** The `ToolExecutor` computes diffs from the worktree with `git diff` (no reliance on the
model's account of its edits — constitution IV):

- After each `EDIT`, a **file-scoped** diff (`git diff -- <path>`) is emitted as `tool.file` `diff`
  so the trace updates incrementally as the Coder works.
- At task end, the **full change set** (`git diff <base>...HEAD` incl. staged) is written to
  `runs/<runId>/artifacts/<taskId>/diff.patch` and referenced in the `TaskResult` as an
  `artifacts[]` entry with `kind: "diff"` (already schema-valid).
- Each event carries a parsed per-file summary (`path`, `status`, `additions`, `deletions`) plus the
  raw unified `patch`, and a `truncated` flag when the patch exceeds the size cap.

**Frontend (VS Code-style).** A small, dependency-free renderer, added under
`frontend/src/components/diff/`:

- `lib/parseUnifiedDiff.ts` — a ~100-line pure parser: unified patch → `files[] → hunks[] → lines[]`
  (`add` / `del` / `context`, with old/new line numbers). Unit-tested with Vitest.
- `DiffView.tsx` + `diff.module.css` — presentational, VS Code inline-diff look:
  - Per-file header: path, a status badge (added/modified/deleted/renamed), and `+adds / −dels`
    counts; **collapsible** (collapsed by default for large files).
  - Single-column hunks with old/new line-number gutters, `+`/`−`/context row coloring using the
    existing theme tokens, monospace. (Side-by-side is a later, additive enhancement.)
  - Oversized/binary diffs degrade to a one-line summary + a "view raw patch" fallback — the
    **Copilot-CLI unified-diff look**, satisfying the spec's "实在不行 copilot cli 那种也行".
- Wired into both surfaces at **search parity**: a new `diff` trace item renders as a `DiffCard` in
  [`TraceTimeline.tsx`](../../frontend/src/components/orchestration/TraceTimeline.tsx) (live + in the
  collapsible per-answer record) and in
  [`ActivityPanel.tsx`](../../frontend/src/components/activity/ActivityPanel.tsx) (after-the-fact),
  exactly where the search-results list renders today.

**Why custom, not a library:** the repo already hand-rolls small renderers (the search-results
`<ol>`) rather than pulling heavy deps; a unified-diff parser is small, keeps the dependency gate
green (constitution engineering standard), and keeps the bundle lean. Richer syntax highlighting can
be layered on later without changing the event contract.

## Project Structure

### Documentation (this feature)

```text
specs/004-tool-execution-layer/
├── spec.md              # done (clarified)
├── plan.md              # this file (Phase 0/1 inlined)
└── tasks.md             # next: /speckit-tasks
```

### Source Code

```text
runtime/roster/
├── workspace.py         # NEW: WorkspaceManager — per-run worktree lifecycle, path allowlist/resolver
├── tools.py             # NEW: ToolExecutor — read/edit/exec + git-diff; timeouts + output caps
├── boundary.py          # NEW: pure classify_action() (tier + inside/outside sandbox); unit-tested
├── agent.py             # EXTEND: generalize the search loop to READ:/EDIT:/EXEC:; emit tool.file/tool.exec
├── orchestrator.py      # EXTEND: replace "what you WOULD do" prompt with the tool protocol; wire
│                        #         tools per capability grant; raise the boundary gate on block
├── events.py            # EXTEND: emit_tool_file / emit_tool_exec / emit_approval_* helpers
├── run_state.py         # REUSE: AWAITING_INPUT for approval pauses (no new state machine)
├── config.py / config_api.py  # EXTEND: operator-designated target-repo path (Setup, spec 003)
└── server.py            # EXTEND: optional POST /api/approvals/{propId} over the resume path

frontend/src/
├── types/events.ts      # NEW event interfaces + KNOWN_KINDS (tool.file, tool.exec, approval.*)
├── types/models.ts      # NEW TraceItem kinds: file/exec/diff/approval; ActivityCategory additions
├── store/handleEvent.ts # NEW reducers: activityFromDiff/Exec, progress pushes at search parity
├── components/diff/
│   ├── DiffView.tsx      # NEW: VS Code-style per-file diff renderer
│   ├── lib/parseUnifiedDiff.ts  # NEW: pure unified-diff parser (Vitest-tested)
│   └── diff.module.css
├── components/orchestration/TraceTimeline.tsx  # EXTEND: DiffCard / ExecCard / ApprovalCard
└── components/activity/ActivityPanel.tsx        # EXTEND: render diff + exec steps in the feed

shared/schemas/task-result.schema.json    # REUSE (diff artifact + blocked_on_* already supported)
shared/schemas/action-proposal.schema.json # REUSE (boundary proposals)
runs/<runId>/artifacts/<taskId>/            # REUSE: diff.patch, build.log, e2e-report/
```

**Structure Decision**: backend logic stays in `runtime/roster/`, factored so the *safety-critical
pure pieces* (`boundary.py`, the path resolver in `workspace.py`, the diff summarizer) are testable
without a model or subprocess. `agent.py` is extended (not rewritten) so the search loop and tool
loop share one code path. The event contract is the seam to the UI; the diff renderer is the only
net-new frontend module.

## Implementation Phases (maps to spec user stories)

- **Phase A — Workspace + tools substrate (US1 + US2, P1) 🎯.** `WorkspaceManager` (worktree
  lifecycle), `boundary.py` (pure classifier), `ToolExecutor` (read/edit/exec + git-diff, timeouts,
  output caps), and the `agent.py` loop generalization. Replace the "WOULD do" subagent prompt with
  the tool protocol and wire tools by capability grant. The boundary gate raises an `ActionProposal`
  and suspends. Exit: SC-001 (diff on disk contains the change), SC-002 (100% of boundary actions
  gated), SC-004 (zero fabricated outputs), SC-006 (runaways terminated).
- **Phase B — Observability + diff display (US3, P2).** Emit `tool.file`/`tool.exec`/`approval.*`;
  add the frontend event types, reducers, `parseUnifiedDiff`, `DiffView`, and the Trace/Activity
  wiring. Exit: SC-003 (from the UI alone, enumerate every command + exit code and open the diff).
- **Phase C — E2E Playwright (US4, P3).** The E2E agent's `EXEC:`-based `playwright-cli` runner
  against a running build; HTML report artifact; read-only against test definitions. Exit: SC-005
  (reported pass/fail matches real app behavior).

Phases A and B ship together as the P1/P2 increment (a doing-Coder is only trustworthy when its
actions are visible); C follows.

## Risks & Mitigations

- **A tool escapes the sandbox** → the allowlist path-resolver + pure `classify_action` are the hard
  line, unit-tested with adversarial paths (`../`, symlinks, absolute paths); writes resolve to a
  real path and MUST be a descendant of the worktree or they are denied.
- **A command hangs / floods output** → per-command timeout kills the process group; output captured
  to a byte cap with a truncation marker; no TTY (stdin closed). Tested with a `sleep`/`yes` command.
- **Weak model emits malformed directives** → strict parser, corrective feedback, bounded tool-call
  budget per turn (mirrors `MAX_SEARCHES_PER_TURN`); the Coder brain is assumed capable (spec 001).
- **Dirty `main` / pre-existing worktree** → `WorkspaceManager` refuses an unclean base and
  reuses/cleanly recreates the run branch; never clobbers unrelated branches.
- **Diff too large to render** → backend caps the patch and sets `truncated`; `DiffView` collapses
  and offers the raw-patch fallback (CLI look). No OOM, no frozen UI.
- **Event/UI drift** → payloads defined here once, typed in `events.py` and `events.ts` together
  (the spec 001/002 discipline); `parseEvent` ignores unknown kinds during rollout.
- **Approval loop oscillation** → a rejected action is abandoned exactly once; the agent proceeds
  without it or reports it cannot complete — the run does not re-propose the same action.

## Complexity Tracking

One deliberate simplification, per the spec's Out of Scope and the engineering-standard note above.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| v1 isolation is worktree + subprocess, not container/VM | Ships a real doing-Coder now on a trusted single-tenant host; container/VM isolation is a large, orthogonal build | A no-isolation "just run it" model was rejected (unsafe); full container isolation was deferred, not skipped — the boundary gate still stops every out-of-sandbox action, so no principle is weakened |

## Next Steps

1. `/speckit-tasks` — break Phases A–C into ordered, independently-shippable tasks. Pure units first
   (`boundary.classify_action`, the worktree path-resolver, the diff summarizer, `parseUnifiedDiff`)
   with tests runnable without a model or network; then the `agent.py` loop + prompt swap; then the
   event emitters + `DiffView`; then the E2E runner. MVP = Phase A + B (a Coder that edits real files
   and shows a real diff, safely gated and fully observable).
2. Keep the new event kinds in lockstep across [`events.py`](../../runtime/roster/events.py) and
   [`events.ts`](../../frontend/src/types/events.ts) (the spec 001/002 seam discipline).
