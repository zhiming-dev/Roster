# Risk Tier Policy — Reference

Two axes collapsed into one ordered scale: **reversibility** × **blast radius**.

```
                blast radius →
                none        local       bounded     wide        critical
reversibility ↓
read-only       T0          T0          T0          T0          T0
trivial         T1          T1          T1          T2          T3
hard            —           T1          T2          T3          T4
irreversible    —           T2          T3          T4          T4
```

## Per-tier rules

### T0 — Read-only
- **Examples:** `cat`, `git log`, `SELECT`, `playwright snapshot`, web search.
- **Policy:** auto-allow; log after the fact.

### T1 — Trivially reversible, local
- **Examples:** write to `runs/<id>/artifacts/`, create a git branch, draft a PR (not publish),
  set a local env var.
- **Policy:** auto-allow; emit `action_proposed` then `action_executed`.

### T2 — Reversible with effort, bounded scope
- **Examples:** `git commit`, push to a *feature* branch, edit a staging config, create a
  resource in a sandbox subscription.
- **Default policy in this repo:** **soft gate** — 15-minute principal-veto window via async
  channel; auto-proceeds if no veto. Override per-task in plan via `riskTier: T2` + a `gateOverride`.

### T3 — Hard to reverse, wide scope
- **Examples:** merge to `main`, deploy to staging, schema migration (with backup), publish a PR,
  rotate a non-prod secret.
- **Policy:** mandatory human approval. Must include `diffPreview` and `reversibilityPlan`.

### T4 — Irreversible or critical
- **Examples:** `DROP TABLE`, `DELETE FROM ... WHERE ...` against prod, force-push `main`,
  deploy to prod, mass-email customers, spend money, rotate a prod secret, public release.
- **Policy:**
  1. The proposing agent **must** have a `recoverabilityState.backupVerified === true` from a
     verification performed within the last 30 minutes by the recoverability subsystem.
  2. The approval gate refuses to even *show* the proposal to the principal until (1) holds.
     If verification fails, the proposal is rejected with `verification_failed` and the task
     must be re-planned (typically: take a fresh snapshot, then resubmit).
  3. The proposal must include a non-empty `diffPreview` from a dry-run.
  4. Approval must be synchronous (CLI / dashboard) — not Slack/email.

## Reclassification rules

- **Up-classify freely.** If you are uncertain whether something is T2 or T3, treat it as T3.
- **Never down-classify after a rejection.** Re-submitting the same logical action under a
  lower tier is a violation. Re-plan the task instead.
- **Compound actions take the max tier of their parts.** A "deploy and then notify" action is
  at least the tier of the deploy.

## Overrides

The principal can set policy overrides per-run by dropping a `runs/<runId>/gate-policy.json`
file matching the structure:

```json
{
  "T2": "require_approval",
  "T3": "require_approval",
  "T4": "require_approval",
  "perKind": {
    "git.push:main": "block",
    "deploy:prod": "require_approval_and_two_person"
  }
}
```

Overrides may only make policy **stricter**, never looser.
