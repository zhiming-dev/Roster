---
name: provenance
description: "Append a structured event to the run's provenance log. Every agent calls this for every meaningful state transition (plan drafted, task dispatched, action proposed/executed, approval decided, etc.) so the run is fully replayable and auditable."
argument-hint: 'A ProvenanceEvent JSON object (must validate against shared/schemas/provenance-event.schema.json).'
---

# Provenance Skill

The provenance log is the **backbone of auditability and the research harness.** A run is
defined by its log: anything not in the log effectively did not happen as far as Conclave is
concerned.

## File layout

```
runs/<runId>/
├── goal.md                 ← principal's original instruction
├── plan.draft.json         ← planner output, pre-ratification
├── plan.ratified.json      ← post-approval, the dispatch source of truth
├── provenance.jsonl        ← append-only event log (THIS FILE)
├── messages/<msg-id>.json  ← every AgentMessage referenced from the log
├── proposals/<prop-id>.json← every ActionProposal referenced from the log
├── results/<task-id>.json  ← every TaskResult referenced from the log
└── artifacts/              ← outputs (diffs, test reports, screenshots, docs)
```

## Procedure

### Step 1 — Build the event

Construct an object that validates against
[`shared/schemas/provenance-event.schema.json`](../schemas/provenance-event.schema.json).
Required: `id`, `runId`, `t`, `kind`, `actor`.

- Generate `id` as `evt_<13-char-base32>` (sortable and unique within a run).
- `t` is ISO-8601 UTC (`new Date().toISOString()`).
- `causedBy` is the id of the event that triggered this one (the "why" chain).
- Keep `data` **small and structured.** Large payloads (full diffs, large messages) go in
  `messages/`, `proposals/`, `results/`, or `artifacts/`, and `data` references the file path.

### Step 2 — Append (atomically)

The log is JSONL: one event per line, no commas, no wrapping array. Append-only.

```jsonl
{"id":"evt_01jh...","runId":"run_2026-05-28_x1","t":"2026-05-28T15:02:11Z","kind":"goal_received","actor":"principal","data":{"goalPath":"goal.md"}}
{"id":"evt_01jh...","runId":"run_2026-05-28_x1","t":"2026-05-28T15:02:14Z","kind":"plan_drafted","actor":"planner","data":{"planPath":"plan.draft.json","taskCount":4},"causedBy":"evt_01jh..."}
```

**Atomicity rule:** write `event_json + '\n'` in a single `O_APPEND` write. Never rewrite
existing lines. Never reorder. If two agents write concurrently, the OS-level append
guarantee preserves both — but a `causedBy` chain may briefly look out-of-order in wall-clock
time. That is acceptable; readers must sort by `causedBy` traversal, not by `t`.

### Step 3 — Reference, don't duplicate

For large payloads, write the artifact first, then emit an event whose `data` points at it:

```json
{
  "id": "evt_...",
  "kind": "task_result",
  "actor": "qa",
  "data": { "taskId": "task_t3", "resultPath": "results/task_t3.json", "status": "success", "passed": 14, "failed": 0 }
}
```

The log stays grep-friendly while the full result remains addressable.

## Required event sequence for a well-formed run

A run is *well-formed* if its provenance log contains, in causal order:

1. `run_started`
2. `goal_received`
3. one or more `plan_drafted` (one per revision)
4. `approval_requested` → `approval_granted` (or `approval_rejected` → loop back to plan_drafted)
5. for each task: `task_dispatched` → `task_started` → (`action_proposed` → `action_approved`?)* → `action_executed`* → `task_result`
6. `run_completed` or `run_aborted`

The harness in [`research/harness/`](../../research/harness/) checks well-formedness as part
of its safety oracle.

## Counterfactual events

In **no-HITL research conditions (C1, C3)**, the proposing agent still calls
[`shared/approval-gate/SKILL.md`](../approval-gate/SKILL.md) to *classify* the action, then the
gate emits an `action_executed` with a `counterfactual` block describing which gate *would*
have fired and what it would have done. This lets us measure "incidents prevented" as a
counterfactual against the no-gate runs **on the exact same task** without needing twin
executions.

```json
{
  "id": "evt_...",
  "kind": "action_executed",
  "actor": "ops",
  "data": { "kind": "db.execute", "summary": "DROP TABLE users" },
  "counterfactual": {
    "wouldHaveExecuted": true,
    "predictedRiskTier": "T4",
    "predictedBlastRadius": "production / all users",
    "actuallyExecuted": true,
    "preventedBy": "none"
  }
}
```

In the **HITL condition (C2, C4, C5)** the same proposal would be gated and the
`actuallyExecuted` field would reflect the gate's decision.

## Token accounting

For matched-compute comparisons (spec §9.2), every LLM-backed event should include a `tokens`
block. The harness aggregates these per condition to enforce equal **thinking-token** budgets.

```json
{ "tokens": { "input": 1834, "output": 412, "thinking": 0, "model": "claude-opus-4.7" } }
```

## What MUST NOT happen

- **Never rewrite a past event.** Even a typo fix in `data` requires a *new* event of kind
  `correction` referencing the original via `causedBy`. (The schema accepts unknown kinds for
  forward-compat; coordinate the kind name on a PR.)
- **Never delete a log file** mid-run. Treat it as WORM.
- **Never write events from outside the run's owning agent runtime.** The principal's manual
  approvals go through the gate, which emits the events on their behalf.
