# Harness

The orchestration that drives the task suite across conditions C1–C5 under matched compute,
collects provenance logs, and produces the per-condition dataset for analysis.

## Pipeline

```
task-suite/*.task.json
        │
        ▼
   ┌────────────┐
   │  harness   │  for each (task × condition × model × seed):
   │            │     1. reset testbed
   │            │     2. configure budget per matched-compute rules
   │            │     3. run the architecture under the condition
   │            │     4. emit runs/<runId>/provenance.jsonl
   │            │     5. score success + safety + recoverability oracles
   └─────┬──────┘
         ▼
   results/<study-id>/<runId>/   (artifacts + scored summary)
         │
         ▼
   analysis/  (notebooks; produces the figures for the paper)
```

## Files

- [`conditions.md`](./conditions.md) — exact configuration of C1–C5.
- [`matched-compute.md`](./matched-compute.md) — how the thinking-token budget is enforced.
- (planned) `replay.py` — re-execute a saved `provenance.jsonl` against the testbed for
  reproducibility.

## Why provenance is the substrate

Every condition emits the **same** event schema (see
[`shared/schemas/provenance-event.schema.json`](../../shared/schemas/provenance-event.schema.json)),
even C1 (single super-agent, no HITL). The super-agent emits `goal_received → plan_drafted →
action_executed* → run_completed` with the planner and the executor collapsed into one
actor. This means:

- The dataset is uniform across conditions.
- Counterfactual fields (would-have-fired-gate) are computed in every condition by running
  the classifier from [`shared/approval-gate/SKILL.md`](../../shared/approval-gate/SKILL.md)
  on each `action_executed` event, regardless of whether the gate was active.
- "Replay" of a run is identical machinery across conditions.
