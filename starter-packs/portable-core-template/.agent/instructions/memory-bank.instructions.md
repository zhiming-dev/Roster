# Memory Bank Instructions

## Purpose

The memory bank preserves project-specific context across chat sessions.

## Location

Memory files live under `.memory-bank/` in repository root.

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
- A design decision is made or changed.
- A reusable project pattern is discovered.
- A recurring pitfall or workaround is confirmed.

## Content Guidance

### activeContext.md

Track:
- Current work focus
- Completed and pending steps
- Active decisions
- Next steps

### learnings.md

Track:
- Project architecture and boundaries
- Tooling and build/test practices
- Known failure modes and mitigations
- Patterns that should be reused

### userDirectives.md

Track user preferences such as:
- Response style
- Decision-making preferences
- Review strictness
- Constraints to always honor
