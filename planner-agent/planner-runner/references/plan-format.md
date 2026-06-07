# Plan Format — Annotated Reference

A `Plan` is a JSON document validating against
[`shared/schemas/plan.schema.json`](../../../shared/schemas/plan.schema.json). This file is the
practical reference: structure, conventions, and worked examples.

## Skeleton

```json
{
  "id": "plan_run_2026-05-28_x1_v1",
  "version": 1,
  "runId": "run_2026-05-28_x1",
  "goal": {
    "text": "<verbatim principal goal>",
    "context": "<optional principal-supplied context>",
    "constraints": ["no production changes without approval", "must run before EOD friday"]
  },
  "tasks": [ /* Task[] */ ],
  "edges": [ { "from": "task_a", "to": "task_b", "kind": "sequence" } ],
  "approvalState": "draft",
  "createdAt": "2026-05-28T15:02:14Z",
  "createdBy": "planner"
}
```

## Task conventions

- **`id`** — short, stable, kebab-case after the prefix. e.g. `task_impl-reset-flow`.
- **`assigneeRole`** — exactly one of `planner | qa | coder | reviewer | researcher | ops | data`.
  If a step needs two roles, it is two tasks with an edge.
- **`requiredCapabilities`** — explicit list. Sub-agents will refuse to act if a tool they need
  is not in the grant. **Grant nothing the task does not actually need.**
- **`riskTier`** — the *maximum* tier any action under this task may reach. Up-tier when
  uncertain.
- **`successCriteria`** — concrete, ideally machine-checkable. "Tests pass" is fine if it
  refers to a specific suite; "code looks good" is not.
- **`expectedArtifacts`** — file paths the sub-agent will write under `runs/<runId>/artifacts/`.
  Used by the reviewer and the harness.
- **`recoverabilityPlan`** — required for T3/T4. Be specific: "`git revert <sha-after-impl>`"
  beats "revert the change".

## Edge conventions

- **`sequence`** — the default. `from` must finish before `to` may dispatch.
- **`data`** — `to` consumes an artifact produced by `from`. Stronger than sequence: a
  re-plan that replaces `from` invalidates `to`.
- **`approval`** — the principal's ratification of an `ActionProposal` from `from` is a
  precondition for `to`. Used to model "after the prod purge is approved AND done, run the
  smoke suite again".

## Worked example — "forgot password" (matches `examples/forgot-password-flow/`)

```json
{
  "id": "plan_run_2026-05-28_x1_v1",
  "version": 1,
  "runId": "run_2026-05-28_x1",
  "goal": {
    "text": "Add a 'forgot password' flow and make sure it works; clean up stale password-reset tokens older than 30 days.",
    "constraints": ["no production changes without approval"]
  },
  "tasks": [
    {
      "id": "task_impl-reset-flow",
      "description": "Implement the forgot-password endpoint + UI on a feature branch. No DB schema change. Include unit tests.",
      "assigneeRole": "coder",
      "requiredCapabilities": ["read:repo", "write:repo:branch", "run:build"],
      "riskTier": "T2",
      "successCriteria": "Feature branch builds; new unit tests pass; PR drafted (not published).",
      "expectedArtifacts": ["diffs/reset-flow.patch", "build-log.txt"],
      "recoverabilityPlan": "Discard the feature branch; nothing merged."
    },
    {
      "id": "task_review-reset-flow",
      "description": "Review the diff against the task's success criteria. Run linters. Comment on the PR.",
      "assigneeRole": "reviewer",
      "requiredCapabilities": ["read:repo", "run:lint", "comment:pr"],
      "riskTier": "T1",
      "successCriteria": "PR has no blocking review comments; lint clean.",
      "dependsOn": ["task_impl-reset-flow"]
    },
    {
      "id": "task_e2e-reset-flow",
      "description": "Run the existing E2E auth suite plus a new 'forgot-password' E2E test against the feature branch deployed to localhost.",
      "assigneeRole": "qa",
      "requiredCapabilities": ["read:repo", "run:tests"],
      "riskTier": "T0",
      "successCriteria": "All auth-suite tests pass; the new forgot-password E2E test passes.",
      "dependsOn": ["task_review-reset-flow"],
      "expectedArtifacts": ["test-results/auth-suite.html"]
    },
    {
      "id": "task_snapshot-prod-tokens",
      "description": "Take a verified snapshot of password_resets in production before any cleanup. Verify the snapshot is restorable.",
      "assigneeRole": "data",
      "requiredCapabilities": ["db:read", "db:snapshot"],
      "riskTier": "T2",
      "successCriteria": "Snapshot id recorded; restore verified on staging.",
      "dependsOn": ["task_e2e-reset-flow"],
      "expectedArtifacts": ["snapshot-id.txt", "verify-restore.log"],
      "recoverabilityPlan": "Snapshots themselves are inert; no rollback needed."
    },
    {
      "id": "task_purge-stale-tokens",
      "description": "Delete rows from production.password_resets where created_at < NOW() - INTERVAL '30 days'. Requires dry-run + verified snapshot from task_snapshot-prod-tokens.",
      "assigneeRole": "ops",
      "requiredCapabilities": ["db:write"],
      "riskTier": "T4",
      "successCriteria": "Row count after equals row count before minus dry-run count; no rows newer than 30d affected.",
      "dependsOn": ["task_snapshot-prod-tokens"],
      "recoverabilityPlan": "Restore from snapshot id recorded by task_snapshot-prod-tokens."
    }
  ],
  "edges": [
    {"from": "task_impl-reset-flow",     "to": "task_review-reset-flow"},
    {"from": "task_review-reset-flow",   "to": "task_e2e-reset-flow"},
    {"from": "task_e2e-reset-flow",      "to": "task_snapshot-prod-tokens"},
    {"from": "task_snapshot-prod-tokens","to": "task_purge-stale-tokens",  "kind": "data"}
  ],
  "approvalState": "draft",
  "createdAt": "2026-05-28T15:02:14Z",
  "createdBy": "planner"
}
```

## Common anti-patterns to avoid

- **One mega-task with `riskTier: T4`** that bundles "implement + review + test + purge". The
  gate then has to either approve everything or reject everything — losing the safety
  granularity that motivates the framework. **Isolate the destructive step.**
- **A "deploy" task without an explicit preceding "snapshot/backup" task** for anything T4.
  The recoverability precondition cannot be met retroactively.
- **Granting `write:repo` (no `:branch`) to the Coder** "just in case". The Coder should
  never have permission to write to `main` directly; that is exactly the action the framework
  ensures goes through a gated Ops task.
- **Adding tasks during dispatch** without revising and re-submitting the plan. Plan and
  enactment are decoupled for a reason.
