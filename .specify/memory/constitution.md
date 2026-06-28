# Roster Constitution

Roster is a human-in-the-loop, hierarchical multi-agent framework. These principles are the
non-negotiable core every spec, plan, and change is measured against. They exist to make
multi-agent work **safe, recoverable, truthful, and explainable** — not merely fast.

## Core Principles

### I. Human-in-the-Loop Is the Point (NON-NEGOTIABLE)

Roster keeps a human in control of multi-agent work. Approval and ratification gates MUST NOT be
skipped — not even when an agent believes it could complete the work directly. Irreversible or
high-stakes actions (risk tier T3–T4) require explicit human confirmation before execution. The
Planner pauses for ratification; the runtime *surfaces* decisions, it never bypasses them. An
autonomous shortcut that removes the human is a violation, however convenient.

### II. Safety & Recoverability Over Speed

The framework is graded on three metrics — performance, safety, recoverability — and the last two
win ties. When uncertain, choose the path that is safer and easier to undo: prefer reversible
operations, conservative risk tiers (up-tier when in doubt), and bounded loops. A fast result the
human cannot understand or unwind is worse than a slower one they can.

### III. Least Privilege & Orchestrator Restraint

Every task is granted the minimum capabilities it needs and no more; when unsure, grant less and
let the specialist surface the gap. The Planner orchestrates — it decomposes, dispatches,
supervises — and never performs irreversible actions itself. Capabilities are never silently
widened; a gap is re-planned, not bypassed.

### IV. Truth Over Plausibility (No Fabrication)

No agent may invent data, numbers, quotes, headlines, citations, or tool output. Every factual
claim MUST be grounded in a real tool result and cite its source; if a lookup returns nothing or
fails, the agent says so plainly. A truthful "I could not retrieve this" is correct; a
realistic-looking fabrication is the exact failure mode this framework exists to prevent.

### V. Everything Observable (Append-Only Provenance)

Every state transition — goal received, plan drafted/revised, approval requested/granted/rejected,
task dispatched, result received, error, run completed/aborted — is emitted as an event to the
append-only provenance log. History is never rewritten; logs and sample traces are immutable. The
system is explainable by construction: a human, or the dashboard, can reconstruct what happened
and why.

### VI. Contracts Are Typed and Validated

Structured artifacts (Plan, Task, ActionProposal, AgentMessage, ProvenanceEvent, CapabilityGrant)
MUST validate against their schema in `shared/schemas/`. The schema is the source of truth — code
conforms to it, not the reverse. Schema changes bump the `$id` version and call out breaking
changes. Inter-process contracts (e.g. the runtime's REST/WebSocket event kinds) are typed and
stable; presentation layers consume them without forcing changes.

## Engineering Standards

- Runtime is Python 3.10+; agents and skills are markdown-first (`.agent.md` / `SKILL.md` with
  YAML frontmatter).
- All times are ISO-8601 UTC. All ids are stable, URL-safe, and kind-prefixed (`plan_`, `task_`,
  `msg_`, `evt_`, `prop_`, `run_`).
- Read-only zones are respected: user test fixtures, sample provenance traces, and in-progress run
  logs are never edited to fit code. Let tests fail honestly rather than rewriting them to pass.
- Use only free / open-source dependencies unless a paid dependency is explicitly approved.
- User-facing surfaces MUST meet WCAG AA and honor `prefers-reduced-motion`, and MUST degrade
  gracefully when the backend is unreachable.
- The standalone runtime stays single-process to deploy (the Python service serves its own UI);
  a presentation rewrite MUST NOT change backend behavior to reach parity.

## Development Workflow & Quality Gates

- Work follows Spec-Driven Development (Spec Kit): Specify → Clarify → Plan → Tasks → Implement,
  with feature artifacts under `specs/<NNN>-<feature>/`.
- Every plan includes a Constitution Check and passes it before implementation. Any violation is
  justified in the plan's Complexity Tracking, naming the simpler alternative and why it was
  rejected.
- Features decompose into independently-shippable, prioritized user stories; the smallest P1
  increment must deliver real value on its own.
- Parity before removal: a replacement is not "done" — and the thing it replaces is not deleted —
  until a parity check passes.

## Governance

This constitution supersedes ad-hoc practice; when it and a convenience conflict, the constitution
wins. Amendments require a written rationale, a semantic version bump, and — for principle changes
that affect existing artifacts — a migration note. Specs and plans cite the constitution version
they were written against. Reviewers reject changes that violate a principle absent a documented,
justified exception.

Versioning is semantic: MAJOR for a backward-incompatible principle change or removal, MINOR for a
new principle or materially expanded guidance, PATCH for clarifications and wording.

**Version**: 1.0.0 | **Ratified**: 2026-06-27 | **Last Amended**: 2026-06-27
