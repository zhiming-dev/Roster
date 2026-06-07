# Dispatch Protocol — Reference

How the Planner invokes expert sub-agents, routes their results, and handles approval
round-trips.

## The dispatch unit: a `task_assignment` message

For each ready task, the Planner writes a message of type `task_assignment`:

```json
{
  "id": "msg_disp_task_impl-reset-flow",
  "runId": "run_2026-05-28_x1",
  "threadId": "thread_task_impl-reset-flow",
  "from": "planner",
  "to": "coder",
  "type": "task_assignment",
  "timestamp": "2026-05-28T15:10:02Z",
  "causedBy": "evt_approval_granted_p1",
  "payload": {
    "task": { /* full Task object copied from the ratified plan */ },
    "capabilityGrant": {
      "agentRole": "coder",
      "taskId": "task_impl-reset-flow",
      "capabilities": ["read:repo", "write:repo:branch", "run:build"],
      "grantedAt": "2026-05-28T15:10:02Z",
      "grantedBy": "planner"
    },
    "runDir": "runs/run_2026-05-28_x1",
    "deadlineHint": "2026-05-28T17:00:00Z"
  }
}
```

The Planner emits `task_dispatched` to provenance referencing this message id.

## Invoking the sub-agent

In a markdown-agent IDE (Copilot, Claude Code, Cursor), "invoking the sub-agent" means: open
the agent file (`<role>-agent/<role>.agent.md`) in a subagent context with the message path as
its input. The sub-agent's first action is always:

1. Read the `task_assignment` message.
2. Read its own `<role>.agent.md` and the skill(s) referenced therein.
3. Read [`shared/approval-gate/SKILL.md`](../../../shared/approval-gate/SKILL.md) and
   [`shared/provenance/SKILL.md`](../../../shared/provenance/SKILL.md).
4. Emit `task_started`.

## Parallel vs sequential dispatch

- Tasks with no edge into each other and no overlapping state may be dispatched **in
  parallel** as separate subagent invocations.
- Tasks connected by a `sequence` or `data` edge are **strictly sequential**; the downstream
  task is dispatched only after `task_result` arrives upstream.
- Two tasks that share state (same file, same row, same env) — even if unconnected by an
  edge — must be serialized. Add the edge in the next revision; for the current run, hold the
  second task until the first returns.

## Receiving a result

Each sub-agent writes its result to `runs/<runId>/results/<task-id>.json` (validating
against [`task-result.schema.json`](../../../shared/schemas/task-result.schema.json)) and
sends a `task_result` message to the Planner. The Planner:

1. Validates the result against the schema.
2. Compares against the task's `successCriteria` and `expectedArtifacts`.
3. Acts on the `status`:

| `status` | Planner action |
|---|---|
| `success` | Mark the task done; dispatch newly-ready downstream tasks. |
| `partial` | Re-plan: add a follow-up task. If the gap is non-trivial, revise the whole plan and request re-ratification. |
| `failure` | Same as partial, but always revise & re-ratify before continuing. |
| `blocked_on_approval` | Check `openProposals[]` exists in `runs/<runId>/proposals/`. Confirm the approval gate is running. Wait. |
| `blocked_on_dependency` | Add the missing prerequisite as a new task; revise the plan. |
| `aborted` | Sub-agent stopped itself for a stated reason. Treat as failure unless the reason is a principal-supplied cancel. |

## Handling an `ActionProposal`

When a sub-agent emits `action_proposed` (see
[`shared/approval-gate/SKILL.md`](../../../shared/approval-gate/SKILL.md)), the Planner's role
is to **notify, not to bypass**:

1. Surface the proposal to the principal via the configured approval channel.
2. **Do not** "pre-approve" or auto-translate the proposal into a different action. The
   Planner is not in the trust chain for irreversible actions.
3. Wait for `approval_granted` or `approval_rejected`.
4. On approval, the sub-agent resumes. On rejection, the sub-agent returns
   `blocked_on_approval`; the Planner re-plans.

## Sub-agent timeout & failure handling

- If a sub-agent does not return within `deadlineHint × 2`, emit `error` to the principal and
  pause the run. Do not auto-retry irreversible work.
- If a sub-agent crashes mid-task with no `task_result`, the Planner reconstructs state from
  the provenance log + any partial artifacts and re-dispatches as a fresh task. The original
  task id is preserved in `causedBy` for traceability.

## What dispatch is NOT

- Dispatch is not a free-form chat between Planner and sub-agent. All bidirectional
  communication uses typed `AgentMessage`s.
- Dispatch is not a way to elevate capabilities. If a sub-agent asks for a capability outside
  its grant, the Planner re-plans (typically by reassigning to a role that legitimately holds
  the capability), not by silently widening the grant.
- Dispatch is not a substitute for the gate. Even on a fully-ratified plan, a T3/T4 action
  inside an approved task still triggers the **Action Gate** (the second gate in the
  architecture diagram). The plan ratification only approves the *shape* of the work, not the
  specific irreversible commands.
