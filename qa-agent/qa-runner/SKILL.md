---
name: qa-runner
description: "Validate and fact-check another agent's output against evidence and the task's success criteria. Use when: verifying a report, fact-checking claims, cross-checking research findings, confirming a result meets its criteria. Not for browser/E2E testing (see e2e-runner)."
argument-hint: "The artifact to validate + the success criteria it should meet"
---

# QA / Validation Runner

The runbook for the **QA / Validation** agent. You receive an artifact (a report, a set of
claims, a research synthesis, a result summary) and a set of success criteria, and you
return a structured verdict.

## When to Use

- Fact-check a report or set of claims (numbers, dates, names, quotes, events).
- Cross-check a Researcher's findings against their cited sources and against the live web.
- Confirm a deliverable actually satisfies the task's `successCriteria`.
- Catch fabricated data — confident, realistic-looking claims with no real source.

This skill is **not** for browser end-to-end testing. That is the
[`e2e-runner`](../../e2e-agent/e2e-runner/SKILL.md) skill on the E2E Test agent.

## Procedure

### Step 0: Parse the assignment

Identify (a) the artifact to validate and (b) the criteria it must meet. If the criteria
are implicit, infer the minimal explicit checklist and state it back.

### Step 1: Extract checkable claims

List the concrete, falsifiable claims in the artifact: every number, date, name, quote,
and cause-and-effect assertion. Vague prose is not a claim; "the Nasdaq fell 4% on
2026-06-05" is.

### Step 2: Verify each claim

For each claim, choose a verdict and back it with evidence:

- **verified true** — confirmed against a credible source (cite the URL).
- **verified false** — a credible source contradicts it (cite it).
- **unsupported** — stated as fact but no source supports it; you could not find one.
- **unverifiable** — inherently cannot be checked (opinion, private data, future event).

For live or external facts, **search the web** rather than trusting the claim or your own
memory. Prefer two independent sources for any number that matters. Note disagreements
instead of silently picking one.

### Step 3: Check consistency & coverage

- **Internal consistency**: do totals match line items, does the summary match the detail,
  are the dates coherent?
- **Criteria coverage**: walk the success criteria one by one; mark each met / partially
  met / unmet with a reason.

### Step 4: Return the verdict

```
Verdict: pass | pass-with-notes | fail
Checked:
- <claim> → verified true | verified false | unsupported | unverifiable  (source: <url>)
Blocking issues: <factual errors, unsupported claims, unmet criteria — or "none">
Notes: <non-blocking observations, style nits, suggested follow-ups>
```

`fail` if there is any verified-false claim, any material unsupported claim, or any unmet
blocking criterion. `pass-with-notes` if only non-blocking issues remain. `pass` only when
the material claims are verified and the criteria are met.

## Anti-patterns (do not do these)

- **Rubber-stamping.** Returning `pass` without actually checking the concrete claims.
- **Trusting a citation you didn't open.** If a claim cites a source, the source must
  actually support it; a plausible-looking URL is not verification.
- **Upgrading "could not verify" to a pass** (or downgrading it to a fail). Report it
  honestly as what it is.
- **Fixing the artifact.** You validate; you do not edit. Hand findings back to the Planner.
- **Style policing as blocking.** Wording preferences are notes, not failures.
