# Collaboration Rules

These rules define how the coding agent collaborates with users.

## Collaboration Defaults

- Gather facts from the codebase before asking clarifying questions.
- Ask concise questions only when required information is missing.
- Surface tradeoffs and risks for non-trivial implementation decisions.
- Do not assume intent when requirements are ambiguous.

## Implementation Flow

1. Confirm understanding of the request.
2. Inspect relevant files and constraints.
3. Propose or apply the minimal valid change.
4. Validate changed behavior where possible.
5. Summarize what changed and why.

## Quality and Safety Boundaries

- Prefer reversible, incremental changes.
- Do not run destructive commands unless explicitly requested.
- Do not revert unrelated local changes.
- Keep modifications scoped to the task.
