# Experimental Conditions

## C1 — Single super-agent, no HITL

- Architecture: one model holding all skills, no decomposition.
- Approval gate: **classify only** (counterfactual). All actions auto-execute.
- Council: n/a.
- Sub-agent invocations: none (the super-agent IS the executor).
- Provenance: still emitted with the super-agent listed as `actor` for both planning and
  enacting events.

## C2 — Single super-agent, HITL on

- Architecture: as C1.
- Approval gate: **active** at the per-action level. T3/T4 actions block on principal approval.
- Council: n/a.
- Provenance: as C1, with `approval_requested` / `action_approved` events.

## C3 — Multi-agent, no HITL, no Council

- Architecture: Planner + expert sub-agents per the full framework.
- Approval gate: **classify only.** Planner still emits plan ratification step but the
  "principal" auto-approves all plans and all action proposals.
- Council: off.
- Provenance: full multi-agent trace, with `auto: true` on every approval event.

## C4 — Multi-agent, HITL on, no Council

- Architecture: as C3.
- Approval gate: **active** for plan ratification AND per-action T3/T4 gates.
- Council: off.
- Provenance: full multi-agent trace including human approvals.

## C5 — Multi-agent, HITL on, Council on

- Architecture: as C4.
- Approval gate: as C4.
- Council: **invoked according to planner policy** (see
  [`shared/council/SKILL.md`](../../shared/council/SKILL.md)) — not on every step, only on
  flagged decision classes.
- Provenance: includes `council_*` events.

## Cross-condition invariants

- Same **model panel.** Each comparison fixes the underlying model; the panel rotation
  studies RQ5 (capability scaling).
- Same **matched thinking-token budget** per (task × condition).
  See [`matched-compute.md`](./matched-compute.md).
- Same **task suite.** No condition gets a task the others don't.
- Same **human approver protocol** for HITL-on conditions. Approvers are blind to condition.
- Same **testbed state.** Reset deterministically before every run from the same seed.

## What is *not* held constant (intentional)

- The number of sub-agents involved (the architecture defines this).
- Wall-clock time (we measure it).
- Cost in USD (we measure it).
- Number of human round-trips (we measure it).

A multi-agent + HITL architecture is allowed to be slower and more expensive than a
super-agent. The study measures whether the safety/recoverability gains are worth the cost —
and on which task classes.
