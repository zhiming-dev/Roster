---
applyTo: "**/*.md,**/*.mdx"
---

# Markdown Authoring Instructions

This repo is markdown-first: agent definitions, skills, specs, and docs are all markdown.
Quality and consistency of these files directly affect agent behavior.

## Goals

- Keep documentation clear, direct, and easy to scan.
- Prefer practical guidance over narrative filler.
- Keep examples realistic and technology-accurate.

## Writing Rules

- Use concise sections and action-oriented headings.
- Keep bullets flat; avoid deep nesting.
- Keep command examples copy/paste friendly (PowerShell on Windows).
- Use relative links for files in the repository.

## Agent & Skill Frontmatter

- Agent files (`<role>.agent.md`): frontmatter must include `description` and `tools`.
- Skill files (`SKILL.md`): frontmatter must include `name`, `description`, and `argument-hint`.
- A skill `description` must state WHEN to use it (trigger phrases and scope) so the model can
  match it to user intent.

## Safety Rules

- Do not include secrets, tokens, or credentials.
- Use placeholders for sensitive values.
- Do not include personal email addresses in examples.

## Quality Rules

- Verify internal links resolve.
- Keep terminology consistent across docs (Planner, Coder, QA, Reviewer, Researcher, E2E).
- Use ISO-8601 UTC for timestamps and the `kind_…` id convention in examples.
- Update docs when behavior or interfaces change.
