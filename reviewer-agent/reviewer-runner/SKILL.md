---
name: reviewer-runner
description: "Review a diff against a task's success criteria. Use when: a `task_assignment` for role `reviewer` lands; you need to lint, summarize a diff, or produce structured review comments."
argument-hint: 'Path to the task_assignment message; the message payload should reference the diff path.'
---

# Reviewer Runner

## When to Use

- The Planner dispatches a `task_assignment` for role `reviewer`.
- An upstream task has produced a diff artifact and a `successCriteria` to review against.

## Prerequisites

- Read [`reviewer.agent.md`](../reviewer.agent.md).
- Read [`shared/approval-gate/SKILL.md`](../../shared/approval-gate/SKILL.md) and
  [`shared/provenance/SKILL.md`](../../shared/provenance/SKILL.md).

## Procedure

1. **Read the task + upstream diff.** Confirm `assigneeRole === "reviewer"` and the
   `inputs.diffPath` points at an existing artifact.
2. **Emit `task_started`.**
3. **Run linters** appropriate for the changed files (`eslint`, `ruff`, `golangci-lint`, etc.).
   Capture output under `runs/<runId>/artifacts/<task-id>/lint.log`.
4. **Read the diff** and judge each hunk against the upstream task's `successCriteria`.
5. **Write the review** at `runs/<runId>/artifacts/<task-id>/review.md` with two sections:
   - **Blocking** — criterion violations, correctness bugs, security issues, missing tests
     for a behavior change. Each item cites `file:line` and the criterion it violates.
   - **Non-blocking** — style, naming, suggestions. Do **not** gate on these.
6. **Post the review** as PR comments (`comment:pr` capability) if the diff is a real PR.
   Otherwise the artifact is the deliverable.
7. **Write the `TaskResult`:**
   - `success` if Blocking is empty and lint is clean.
   - `partial` if lint has warnings but no errors and no Blocking items.
   - `failure` if any Blocking item or any lint error.
8. **Emit `task_result`** and message the Planner.

## Anti-patterns

- **"Approving with one nit"** but listing five style preferences as Blocking. Be honest about
  what is and isn't a gate.
- **Reviewing for what you wish the task were** instead of for the success criteria the
  principal ratified. If the criteria are wrong, surface that as a message to the Planner —
  do not fail the diff for not matching your imagined criteria.
- **Modifying the diff.** Reviewer never writes source. If a fix is small and obvious, propose
  it in a comment; do not commit it yourself.

## Status

🚧 **Scaffold.**
