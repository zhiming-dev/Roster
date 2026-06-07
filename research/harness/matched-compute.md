# Matched-Compute Accounting

The most common methodological problem in published multi-agent-vs-single-agent comparisons is
that the multi-agent system gets **far more thinking compute** at inference time (one
"planner" call plus N "expert" calls plus M "debate" rounds — vs the single agent's one call).
When this is controlled for, single-agent often matches or beats multi-agent on multi-hop
reasoning (Tran & Kiela 2025; see [`conclave-spec.md` §10](../../conclave-spec.md)).

We therefore enforce **matched thinking tokens** at the (task × condition) level.

## Definitions

- **thinking tokens** — the model's internally-billed thinking/reasoning tokens (e.g. Claude's
  thinking, GPT's reasoning effort, Gemini's thinking). We sum across **all** LLM calls a
  condition makes for the task — planner, every sub-agent invocation, every Council message,
  every retry.
- **task budget** — a per-task thinking-token cap, set by the most-permissive condition
  needed to solve the task to spec, then applied uniformly.

## Calibration procedure

1. For each task in the suite, run a calibration sweep under **C3** (multi-agent, no HITL — the
   most token-hungry non-Council condition) at increasing budgets until success rate plateaus.
   Call the plateau budget $B^*$.
2. For each (task × condition), set the budget to $B^*$ regardless of condition. The
   single-super-agent conditions (C1, C2) get the same $B^*$ — typically far more thinking
   compute than they would ordinarily use.
3. C5 (with Council) may exceed $B^*$ — record the overrun explicitly and report it as a
   cost penalty when comparing to C4.

The tolerance band is **±5% of $B^*$**. A condition that hits the budget without success is
recorded as failure at budget exhaustion; that is a valid datapoint.

## Per-call accounting

Every `ProvenanceEvent` from an LLM call carries a `tokens` block:

```json
{ "tokens": { "input": 0, "output": 0, "thinking": 0, "model": "..." } }
```

The harness sums `thinking` across all events for the run and reports:

- `tokens.thinking.total` — primary control variable
- `tokens.input.total` + `tokens.output.total` — secondary, for cost analysis in USD
- `tokens.thinking.byActor` — for understanding where the budget went

## Reporting

In the paper, every per-task metric is reported **both** per-task (raw) **and**
per-thinking-token (normalized). This separates "the architecture wins" from "the
architecture spent more compute" claims.

## Caveats

- **Provider differences.** Anthropic, OpenAI, Google count thinking differently. We use each
  provider's billed thinking-token field and report per-provider results separately as well as
  pooled. Comparisons that mix providers within one condition are clearly marked.
- **Sub-agent vs super-agent context tax.** A multi-agent system pays a serialization tax
  (each sub-agent has to be re-introduced to its context). This counts against its budget — it
  is part of the architecture's real cost.
- **Council token multiplier.** Council is allowed to exceed $B^*$ only when its policy says
  to convene (selective invocation). A run that convenes the Council on every step is itself
  a failure of policy and is recorded as such.
