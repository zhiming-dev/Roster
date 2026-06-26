# Spec Kit (Spec-Driven Development)

Spec Kit is the open-source [github/spec-kit](https://github.com/github/spec-kit)
toolkit. It adds a structured Specify → Plan → Tasks → Implement workflow with
review gates, driven by `/speckit-*` chat commands.

This folder is **not Microsoft-internal** — it is the public Spec Kit structure.

## What is included here

- `templates/` — the customizable spec, plan, tasks, checklist, and constitution templates
- `memory/constitution.md` — your project principles (edit this or run `/speckit-constitution`)
- `init-options.json` — Spec Kit init configuration

The `/speckit-*` commands are provided by the matching skills under
`.github/skills/speckit-*` and the prompt under `.github/prompts/`.

## Two ways to enable Spec Kit in a new repo

### Option A — Official initializer (recommended)

Use the official tool so the helper scripts stay current:

```bash
# Requires uv (https://github.com/astral-sh/uv)
uvx --from git+https://github.com/github/spec-kit.git specify init --here --ai copilot --script ps
```

This generates the `.specify/scripts/` helpers, the templates, and wires the
chat commands for GitHub Copilot. Then customize `memory/constitution.md` and
the `templates/` to fit your project.

### Option B — Copy this bundled structure

1. Copy this `.specify/` folder into your target repo root.
2. Copy the `.github/skills/speckit-*` skills and `.github/prompts/` Spec Kit
   prompt (the chat commands).
3. Generate the helper scripts once with Option A, or author equivalents under
   `.specify/scripts/powershell/`.

## Typical workflow

1. `/speckit-constitution` — set project principles
2. `/speckit-specify` — describe the feature, generate the spec
3. `/speckit-clarify` — resolve open questions
4. `/speckit-plan` — produce the implementation plan
5. `/speckit-tasks` — break the plan into ordered tasks
6. `/speckit-implement` — execute tasks with review gates

## Notes

- Keep generated feature work under `specs/<NNN>-<feature>/`.
- The constitution is the quality gate referenced by every plan.
- Nothing in Spec Kit requires internal Microsoft services.
