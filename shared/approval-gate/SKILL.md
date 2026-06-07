---
name: approval-gate
description: "Classify a proposed action's risk tier (T0–T4), apply the gate policy, and (if required) summarize the proposal into a human-reviewable approval request. Use whenever an agent is about to perform an action that touches anything outside its own scratch state."
argument-hint: 'An ActionProposal JSON path or inline object. Optional: --policy <policy-file>.'
---

# Approval Gate Skill

The approval gate is the structural mechanism by which Conclave **decouples decision from
enactment**. Every agent calls this skill before any action that touches the environment.

## When to use

- A sub-agent is about to invoke a tool that mutates state (filesystem, repo, DB, network, infra).
- The planner is about to dispatch a plan to the execution plane (the plan itself goes through a
  gate the first time it's ratified).
- Any agent encounters an ambiguous or unexpectedly-large action (escalate up tiers when unsure).

## Procedure

### Step 1 — Build an `ActionProposal`

Populate every required field of
[`shared/schemas/action-proposal.schema.json`](../schemas/action-proposal.schema.json):

- `action.kind`, `action.summary`, `action.target`, `action.command` (if applicable)
- `rationale` — reference the ratified plan + this task's `successCriteria`
- `reversibilityPlan` — "git revert <sha>", "drop snapshot <id>", or literally `"IRREVERSIBLE"`
- `recoverabilityState` — `backupVerified: true` is **mandatory** for T4
- `diffPreview` — required for T3+, strongly recommended for T2
- `blastRadius` — scope + a count or description of affected entities

### Step 2 — Classify the risk tier

Use this decision table (full version: [`references/risk-tier-policy.md`](./references/risk-tier-policy.md)):

| Tier | Reversibility | Blast radius | Examples |
|---|---|---|---|
| **T0** | n/a (read-only) | none | read file, SELECT, run tests, search web |
| **T1** | trivially reversible | local/sandbox | write to scratch dir, create branch, draft PR |
| **T2** | reversible with effort | bounded | commit, push to feature branch, modify staging config |
| **T3** | hard to reverse | wide | merge to main, deploy to staging, schema migration |
| **T4** | irreversible | critical | `DROP TABLE`, force-push main, deploy to prod, mass-email, spend money |

**When in doubt, classify up.** Mis-classifying T3 as T2 is a safety bug. Mis-classifying T1 as
T2 is at worst friction.

### Step 3 — Apply the policy

Default policy (override in `runs/<runId>/gate-policy.json` if the principal supplies one):

| Tier | Default policy |
|---|---|
| T0 | **allow** — emit `action_executed` after the fact |
| T1 | **allow + log** — emit `action_proposed` then `action_executed` |
| T2 | **notify + auto-allow** OR **soft gate** (per repo config). Default for this repo: **soft gate** (15-minute window to veto). |
| T3 | **mandatory human approval** — block until `approval_granted` |
| T4 | **mandatory human approval + recoverability precondition** — refuse to even *request* approval unless `recoverabilityState.backupVerified === true` |

If the policy says "block", **stop**. Do not execute. Emit `action_proposed` to the provenance
log and write the proposal to `runs/<runId>/proposals/<id>.json`.

### Step 4 — Summarize for the human (T2 soft gate, T3, T4)

The approval request the principal sees **must not be a JSON dump.** It is a short,
opinionated summary:

```
[T4 — IRREVERSIBLE] Coder agent wants to: delete 4,213 password-reset tokens older than 30 days.

  Target:        production.password_resets (postgres-prod)
  Command:       DELETE FROM password_resets WHERE created_at < NOW() - INTERVAL '30 days';
  Affects:       4,213 rows (dry-run on snapshot_2026-05-28_pre)
  Reversibility: restore from snapshot_2026-05-28_pre  ✓ verified 2 min ago
  Rationale:     task_t4 of plan_p1 ("clean up stale tokens"); criteria require ≤30d retention.

[a]pprove  [r]eject  [e]dit  [v]iew-full-proposal  [d]ry-run-again
```

Approval channels supported (any one is sufficient):

- **CLI** — interactive prompt blocking the planner.
- **Async dashboard** — write the proposal to the dashboard's queue; planner waits on a webhook.
- **Slack / email** — same pattern, longer SLAs; non-urgent only.

### Step 5 — Record the decision

On `approve`:

1. Update the proposal's `decision`, `decidedBy`, `decidedAt`.
2. Emit `action_approved` to the provenance log.
3. **Now** the agent may execute. After execution, emit `action_executed` (or `action_failed`)
   with the result.

On `reject` or `request_changes`:

1. Update the proposal accordingly.
2. Emit `action_rejected`.
3. The proposing agent receives a `task_result` with status `blocked_on_approval` and the
   principal's comment. It may re-plan or escalate to the Planner.

## Anti-patterns

- **Do not** re-classify an action *down* after the principal rejects it to try again. That is
  the agent attempting to launder a dangerous action through a lower gate. Emit
  `action_rejected` and return.
- **Do not** batch many T3/T4 actions behind one approval. Each gets its own proposal.
- **Do not** treat "the user is busy" as license to auto-allow. Use async channels and a wait
  state; the gate is not optional.
- **Do not** write `backupVerified: true` without a real verification. If you cannot verify a
  backup for a T4 action, the gate refuses the request and you must fall back to T3 (which
  cannot enact the irreversible operation) — typically meaning the task itself must be re-planned.

## Counterfactual recording (for the safety study)

If running under the research harness in a no-HITL condition (C1, C3), the agent still computes
the proposal and tier, but the harness records a `counterfactual` block on the
`action_executed` event noting which gate *would have* fired. This is how
[`research/`](../../research/) measures "incidents prevented by gates" without needing two
separate runs.
