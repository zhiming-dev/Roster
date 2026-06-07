# Research

The empirical study that ships alongside the framework. The goal is a controlled comparison
of **single super-agent vs multi-agent + HITL** on performance, safety, and recoverability,
under **matched compute**, suitable for peer-reviewed publication.

Full design is in [`conclave-spec.md` §9](../conclave-spec.md). This directory holds the
scaffolding and templates referenced from the spec.

```
research/
├── README.md                       ← (this file)
├── preregistration.template.md     ← copy + fill in before running the study
├── testbed/                        ← sandboxed environment + tripwires
│   └── README.md
├── task-suite/                     ← tasks (ordinary, parallelizable, trap)
│   ├── README.md
│   ├── task.schema.json
│   └── examples/                   ← starter tasks
├── harness/                        ← drives conditions C1–C5 with matched budgets
│   ├── README.md
│   ├── conditions.md
│   └── matched-compute.md
└── results/                        ← (gitignored) per-run artifacts written by the harness
```

## Research questions (recap)

- **RQ1 (Performance).** Under matched compute, single super-agent vs multi-agent + HITL on
  task success rate, latency, cost.
- **RQ2 (Safety).** Does HITL gating reduce destructive-action rate & severity, at what
  throughput cost?
- **RQ3 (Recoverability).** When a bad action happens, how do architectures differ in MTTR
  and % recoverable?
- **RQ4 (Deliberation).** Does cross-model Council improve decision quality on
  high-uncertainty calls — and when does it just cause conformity?
- **RQ5 (Capability scaling).** Do multi-agent advantages shrink as the underlying model
  improves?

## Experimental conditions

| Condition | Architecture | HITL | Council |
|---|---|---|---|
| C1 | Single super-agent | off | — |
| C2 | Single super-agent | on  | — |
| C3 | Multi-agent | off | off |
| C4 | Multi-agent | on  | off |
| C5 | Multi-agent | on  | on  |

Compute control: matched **thinking-token budget**, not just wall-clock. See
[`harness/matched-compute.md`](./harness/matched-compute.md).

## How to participate

- **Add a task** → drop a `*.task.json` under `task-suite/` validating against
  `task-suite/task.schema.json`. Include a `safetyOracle` so the harness can detect
  destructive-action incidents.
- **Add a tripwire** → see [`testbed/README.md`](./testbed/README.md).
- **Reproduce a result** → clone the run's `runs/<runId>/` directory from `results/` and
  replay `provenance.jsonl` through the harness.

The pre-registration template should be filled in **before** the first scored run, then frozen
under version control. See [`preregistration.template.md`](./preregistration.template.md).
