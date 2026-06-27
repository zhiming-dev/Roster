# Memory Bank Instructions

## Purpose

The memory bank preserves Roster-specific context across chat sessions.

## Location

Memory files live under `.memory-bank/` in the repository root.

## Required Files

- `.memory-bank/activeContext.md`
- `.memory-bank/learnings.md`
- `.memory-bank/userDirectives.md` (optional)

## Session Start Behavior

At the start of each new chat session:

1. Read `.memory-bank/activeContext.md`.
2. Read `.memory-bank/learnings.md`.
3. If present, read `.memory-bank/userDirectives.md`.

## Update Behavior

Update memory files when one of these happens:

- A meaningful implementation milestone is completed.
- A design decision is made or changed (e.g. a schema or agent-contract change).
- A reusable project pattern is discovered.
- A recurring pitfall or workaround is confirmed.

## Content Guidance

### activeContext.md

Track current work focus, completed/pending steps, active decisions, and next steps.

### learnings.md

Track project architecture and boundaries, tooling and run practices, known failure modes and
mitigations, and patterns that should be reused.

### userDirectives.md

Track stable user preferences: response style, decision-making preferences, review strictness,
and constraints to always honor.

## Note

These per-developer memory files (`activeContext.md`, `learnings.md`, `userDirectives.md`) are
gitignored by default — only `.memory-bank/README.md` is tracked. Keep entries concise and
specific to this repository.
