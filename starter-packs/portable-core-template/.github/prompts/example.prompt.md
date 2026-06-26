---
mode: agent
description: Example reusable prompt. Copy this file and adapt it to a repeatable workflow in your project.
---

Perform <the repeatable task> for this repository.

Steps:
1. Gather context: read the relevant files and confirm current state.
2. Apply the change following repository conventions.
3. Validate: build and/or run tests for the affected area.
4. Summarize what changed and any follow-ups.

Constraints:
- Keep the diff minimal and focused.
- Do not introduce secrets or unrelated refactors.
- Ask before taking irreversible actions.
