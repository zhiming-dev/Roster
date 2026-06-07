# Contributing to Conclave

Thanks for your interest. This is an open R&D project — issues, PRs, and study
collaborations are all welcome.

## Before you start

1. Read [`README.md`](./README.md) and at minimum sections **2 (Motivation)**,
   **5 (Architecture)**, **6 (Components)**, and **9 (Research plan)** of
   [`conclave-spec.md`](./conclave-spec.md).
2. Read [`AGENTS.md`](./AGENTS.md) — the conventions live there.

## What's in scope

- New expert sub-agents (e.g., Ops, Researcher, Data) that fit the role/skill/capability model.
- New reusable skills under `shared/` or under an existing agent's runner directory.
- Schema improvements with a clear migration path.
- Research artifacts: task-suite tasks (especially **trap tasks**), testbed tripwires, harness
  improvements, analysis notebooks.
- Documentation, worked examples, and reproductions.

## What's out of scope (for now)

- Removing the human-in-the-loop gate. HITL is a feature, not a limitation
  (see [`conclave-spec.md` §3.2](./conclave-spec.md)).
- Model-training PRs. Conclave orchestrates frontier/open models; it does not train them.
- Vendor-specific lock-in. Agents must remain bindable to any model interface.

## Ground rules

- **Least privilege.** A new sub-agent must declare the *minimum* capability set its task needs.
- **Reversibility-aware.** Any new tool must declare its default risk tier
  (see [`shared/approval-gate/SKILL.md`](./shared/approval-gate/SKILL.md)).
- **Everything is logged.** New actions emit provenance events
  ([`shared/provenance/SKILL.md`](./shared/provenance/SKILL.md)).
- **Don't silently rewrite test/criteria/intent artifacts** to make things pass — same rule the
  QA agent enforces in its `SKILL.md`. Failing-loud is a feature.

## PR checklist

- [ ] Linked to an issue or a section of the spec.
- [ ] Updated schemas (if changed) and bumped `$id` version.
- [ ] Updated [`shared/skills.registry.yaml`](./shared/skills.registry.yaml) (if you added a skill).
- [ ] Added/updated an entry in `AGENTS.md` if you added an agent.
- [ ] No breaking change to an in-progress run's `provenance.jsonl` format without a migration note.

## Research contributions

If you contribute tasks to `research/task-suite/`, please include:

- machine-checkable `successCriteria`,
- a **safety oracle** (what would count as a destructive incident on this task), and
- the intended condition coverage (C1–C5) — see [`conclave-spec.md` §9.2](./conclave-spec.md).

## Code of conduct

Be kind; assume good faith; argue ideas, not people. Disagreement is welcome and
expected — it is, after all, the point of the Council layer.
