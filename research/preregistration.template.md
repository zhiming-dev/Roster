# Pre-Registration — Conclave Study (TEMPLATE)

> Fill this out **before** running any scored experiments. Commit the filled version to
> `research/preregistration.v<n>.md`. Changes after the freeze must add a dated amendment
> section rather than rewriting history.

## Title

Single super-agent vs human-in-the-loop multi-agent on performance, safety, and recoverability,
under matched compute.

## Authors and affiliations

(filled in)

## Date of registration

YYYY-MM-DD

## Background and motivation

(1–2 paragraphs — see [`conclave-spec.md` §2, §10](../conclave-spec.md) for the framing)

## Research questions

- RQ1 (Performance), RQ2 (Safety), RQ3 (Recoverability), RQ4 (Deliberation), RQ5 (Capability scaling).
  Full text: [`README.md`](./README.md).

## Hypotheses

- **H1 (Performance, RQ1).** Under matched thinking-token budgets, single-super-agent C1 will
  match or exceed multi-agent C3 on task success rate on routine, single-context tasks. The
  gap will narrow or invert on tasks requiring orthogonal expertise.
- **H2 (Safety, RQ2).** HITL-on conditions (C2, C4, C5) will exhibit at least an **80%
  reduction** in severity-weighted destructive-action incident score vs their HITL-off
  counterparts (C1, C3), on the trap-task subset.
- **H3 (Recoverability, RQ3).** On incidents that do occur, HITL-on conditions will have
  **smaller MTTR** and **higher % recoverable** because the recoverability precondition on
  T4 surfaces snapshot gaps before incidents.
- **H4 (Deliberation, RQ4).** Council (C5) will improve decision quality vs C4 only on
  **high-uncertainty** tasks (those where any single sub-agent's confidence is < 0.7);
  on the rest, C5 will add cost without measurable quality gain.
- **H5 (Capability scaling, RQ5).** All multi-agent advantages over single-super-agent shrink
  monotonically as model capability increases across the model panel.

## Experimental design

- **Conditions:** C1–C5 (see [`harness/conditions.md`](./harness/conditions.md)).
- **Independent variables:** architecture (single / multi), HITL (on / off), Council (on / off),
  underlying model (panel of N — to be enumerated below).
- **Dependent variables:** see Metrics.
- **Compute control:** matched thinking-token budget per task per condition. Tolerance ±5%.
  Methodology: [`harness/matched-compute.md`](./harness/matched-compute.md).
- **Task suite:** see [`task-suite/`](./task-suite/). Three task classes:
  ordinary (single-context implementation), parallelizable (independent subtasks),
  trap (ambiguous/adversarial — designed to tempt destructive shortcuts).
- **Replication:** each (task × condition × model) cell is run **N = 5** times with seed
  variation. Aggregated by median + 95% CI.
- **Human approver role:** human approvers are blind to condition. Approval channel is
  identical across HITL-on conditions to control for UX confounds.

## Metrics (preregistered)

| Dimension | Metric | Direction |
|---|---|---|
| Performance | Task success rate vs `successCriteria` | higher better |
| Performance | Tokens per task (input + output + thinking, all agents) | lower better |
| Performance | Wall-clock per task (excluding approval wait) | lower better |
| Performance | # human round-trips per task | lower better |
| Safety | Destructive-action incident rate | lower better |
| Safety | Severity-weighted incident score (T0..T4 weights = 0,1,3,9,27) | lower better |
| Safety | Counterfactual catches (gate would have fired in a no-HITL condition) | higher better |
| Recoverability | MTTR per incident | lower better |
| Recoverability | % incidents successfully rolled back | higher better |
| Transparency | Provenance completeness (% of actions traceable to ratified plan) | higher better |

Primary safety metric: **severity-weighted incident score on the trap-task subset.**
Primary performance metric: **success rate on the ordinary-task subset under matched compute.**

## Statistical plan

- Per (architecture × HITL × Council) cell, report median + 95% bootstrap CI.
- Primary comparisons: paired (per-task) tests across conditions, holding model fixed.
- Effect sizes (Cohen's d for continuous; risk ratios for incident rates) reported alongside p-values.
- Multiple-comparison correction: Holm–Bonferroni across the H1–H5 family.
- A secondary predictive model: which task features (parallelizability, ambiguity, capability
  demand, irreversibility) predict the architecture-induced delta?

## What would falsify each hypothesis

- **H2 falsified** if HITL-on conditions show < 30% reduction in severity-weighted incident
  score on trap tasks, OR if HITL throughput cost exceeds 4× wall-clock vs HITL-off on
  routine tasks.
- **H4 falsified** if Council (C5) improves decision quality across the board with no
  uncertainty interaction, OR if Council reduces quality on low-uncertainty tasks
  (the conformity-pressure failure mode).
- (etc.)

## Stopping rules

- Stop the study early **only** if a critical safety bug in the harness is discovered.
  Resume after a publicly-documented patch + reproducibility re-check.
- Do **not** add or drop tasks mid-study. Amendments require a numbered registration version.

## Data, code, and reproducibility

- All code: this repo, MIT.
- Per-run artifacts: `runs/<runId>/` directories archived under `research/results/`.
- Aggregated dataset + analysis notebooks: `research/analysis/` (added before submission).
- A reviewer can reproduce any figure with: `python -m research.harness.replay <runId>`
  (script TBD — tracked in the issue list).

## Conflicts of interest

This research is conducted **independently** of the author's employment at Microsoft, and
outside the scope of normal employment responsibilities. Originated from exploratory
prototyping during an internal hackathon; continues as open-source R&D. No funding or
direction from any employer.
