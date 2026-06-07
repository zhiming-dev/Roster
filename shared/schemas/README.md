# Shared Schemas

JSON Schema (Draft 2020-12) definitions for the artifacts that move between agents.
**Every JSON artifact in a run validates against one of these schemas.** If a schema
changes, bump its `$id` version and add a migration note in the PR.

| Schema | What it describes | Lives in a run as |
|---|---|---|
| [`plan.schema.json`](./plan.schema.json) | The ratifiable plan produced by the planner | `runs/<id>/plan.draft.json`, `plan.ratified.json` |
| [`task.schema.json`](./task.schema.json) | One node in the plan DAG | embedded in plan; copied to `runs/<id>/messages/<msg>.json` on dispatch |
| [`task-result.schema.json`](./task-result.schema.json) | A sub-agent's structured result | `runs/<id>/results/<task>.json` |
| [`action-proposal.schema.json`](./action-proposal.schema.json) | A sub-agent's request to perform a gated action | `runs/<id>/proposals/<prop>.json` |
| [`agent-message.schema.json`](./agent-message.schema.json) | Any inter-agent or agent↔principal message | `runs/<id>/messages/<msg>.json` |
| [`provenance-event.schema.json`](./provenance-event.schema.json) | One line of the append-only event log | `runs/<id>/provenance.jsonl` |
| [`capability-grant.schema.json`](./capability-grant.schema.json) | Least-privilege capabilities attached to one (agent, task) pair | embedded in dispatch message |

## Design notes

- **Refs are local.** Cross-schema `$ref`s use bare filenames (e.g. `task.schema.json`), so the
  schemas resolve against this directory regardless of where the repo is cloned.
- **Ids are typed and stable.** Every id is prefixed by kind (`plan_…`, `task_…`, `evt_…`, …) so
  grep-ability is trivial across logs.
- **The provenance log is the canonical source.** Any other artifact can be reconstructed from a
  faithful replay of `provenance.jsonl`. Treat the log as append-only.
- **Counterfactual fields exist on `ProvenanceEvent`** because the safety study (spec §9.3) needs
  to record *what would have happened* if a gate had been auto-allowed, alongside what actually
  happened. Do not strip these fields when serializing for research use.
