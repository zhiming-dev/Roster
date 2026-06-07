---
name: coder-runner
description: "Implement one task on a feature branch. Use when: the Planner has dispatched a `task_assignment` to the Coder role; reading existing code; producing a diff; running a local build."
argument-hint: 'Path to the task_assignment message, e.g. runs/<runId>/messages/<msg>.json'
---

# Coder Runner

## When to Use

- A `task_assignment` for role `coder` lands in `runs/<runId>/messages/`.
- A re-plan from the Planner asks you to patch a follow-up gap.

## Prerequisites

- Read [`coder.agent.md`](../coder.agent.md).
- Read [`shared/approval-gate/SKILL.md`](../../shared/approval-gate/SKILL.md) and
  [`shared/provenance/SKILL.md`](../../shared/provenance/SKILL.md).
- Know [`shared/schemas/task.schema.json`](../../shared/schemas/task.schema.json) and
  [`task-result.schema.json`](../../shared/schemas/task-result.schema.json).

## Procedure

1. **Read the task.** Parse the `task_assignment` message. Confirm:
   - `assigneeRole === "coder"`.
   - `requiredCapabilities ⊆ your_grant`. If not, return `blocked_on_dependency`.
   - `riskTier ≤ T2`. T3/T4 work belongs to Ops; refuse and surface.
2. **Emit `task_started`** to provenance.
3. **Work on a feature branch.** Create / check out `feat/<runId>-<task-slug>`. All writes go
   here. No edits to `main`, `release/*`, `e2e-agent/e2e-test/test-definitions/**`, or any path
   outside the repo's source tree.
4. **Build locally** with `run:build`. Capture the build log under
   `runs/<runId>/artifacts/<task-id>/build.log`.
5. **Run the smallest test signal you have** (unit tests for the area you changed). If you do
   not have `run:tests`, that is fine — the QA agent will pick it up downstream.
6. **Produce a diff artifact** at `runs/<runId>/artifacts/<task-id>/diff.patch`.
7. **Write the `TaskResult`.** `status: success` if criteria met; `partial` with explicit
   gaps if not; `failure` if the work cannot be completed within the grant.
8. **Emit `task_result`** to provenance and send the message to the Planner.

## Gate-aware behavior

Any action above T2 (push to main, deploy, mass file deletion, etc.) is **not your job**.
Emit an `ActionProposal` describing what should be done, return
`status: blocked_on_approval`, and let the Planner reassign.

## Status

🚧 **Scaffold** — runner is documented; implementation TBD.
