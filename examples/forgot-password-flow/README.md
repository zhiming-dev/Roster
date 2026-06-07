# Example — Forgot-password flow (worked end-to-end trace)

A complete, fictional but realistic run that exercises every part of the framework:
plan ratification, sequential hand-off (Coder → Reviewer → QA), a recoverability
precondition (snapshot), a T4 action (mass delete), and the gate catching a destructive
shortcut.

This mirrors **Appendix A** of [`conclave-spec.md`](../../conclave-spec.md).

## Files in this example

| File | Role |
|---|---|
| [`goal.md`](./goal.md) | The principal's verbatim goal |
| [`plan.draft.json`](./plan.draft.json) | Planner's first proposal — flagged for revision |
| [`plan.ratified.json`](./plan.ratified.json) | Post-revision plan that the principal approves |
| [`action-proposal.purge-tokens.json`](./action-proposal.purge-tokens.json) | The T4 delete proposal at the heart of the run |
| [`provenance.sample.jsonl`](./provenance.sample.jsonl) | Full append-only event log for the run |
| [`super-agent-contrast.md`](./super-agent-contrast.md) | What a single-model super-agent does on the same goal — and why it fails |

## The story in 60 seconds

1. Principal asks for a forgot-password flow + cleanup of stale reset tokens older than 30 days.
2. Planner drafts a plan. The principal **rejects v1** because the cleanup task lacked a
   `WHERE` predicate and had no recoverability precondition.
3. Planner produces **v2**: adds a `task_snapshot-prod-tokens` step before the delete,
   tightens the `WHERE`, and explicitly marks the delete `T4`. Principal **ratifies**.
4. Coder implements the feature on a branch. Reviewer approves the diff. QA runs the auth
   E2E suite + a new forgot-password test — 14 passed, 1 failed.
5. Planner re-dispatches Coder to fix the failing test; QA re-runs → all pass.
6. Data agent takes a verified snapshot of `password_resets` and restores it on staging to
   prove restorability.
7. Ops agent proposes the T4 delete with a dry-run diff ("would delete 4,213 rows") and a
   `recoverabilityState.backupVerified: true`. Principal reviews and approves.
8. Ops executes; an undo entry is registered. Planner emits `run_completed`.

## What this prevents

The contrast file shows a single-model super-agent, given the same goal under no HITL gates,
issuing `DELETE FROM password_resets;` (no `WHERE`), wiping all tokens. The same Conclave
plan classifies that exact statement as T4, requires a backup precondition that fails the
verification step for an unscoped delete, and surfaces a dry-run diff showing
full-table deletion before any human approves — at which point the missing `WHERE` is caught.

That is the "9-second `DROP TABLE`" failure mode the framework exists to bound.
