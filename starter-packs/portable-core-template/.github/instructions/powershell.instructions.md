---
applyTo: "**/*.ps1,**/*.psm1,**/*.psd1,**/*.ps1xml"
---

# PowerShell Authoring Instructions

## Goals

- Write predictable, maintainable automation scripts.
- Make scripts safe by default.
- Keep behavior explicit and observable.

## Script Design Rules

- Use parameter blocks with clear names and validation where useful.
- Prefer approved verbs and descriptive function names.
- Use `Set-StrictMode -Version Latest` in non-trivial scripts.
- Emit actionable error messages with context.

## Safety Rules

- Do not hardcode credentials or secrets.
- Validate destructive operations with explicit flags (for example `-Force`).
- Support `-WhatIf` for scripts that mutate external state where practical.

## Quality Rules

- Keep functions short and single-purpose.
- Avoid alias-heavy syntax in committed scripts.
- Document examples for non-obvious usage.
- Preserve idempotency when scripts may run repeatedly.
