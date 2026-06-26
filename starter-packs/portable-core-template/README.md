# Portable Copilot Core Template

This folder contains a portable, compliance-safe Copilot setup you can copy into another repository.

It includes only reusable foundations:
- Repository-specific Copilot guidance
- Session startup guardrails
- Persistent memory workflow
- File-type-scoped instructions (Markdown and PowerShell)
- A repo-expert chat mode
- Example prompt and example skill scaffolds
- Spec Kit (open-source spec-driven development) templates and config
- A sanitized MCP config example

It does not include internal-only dependencies:
- No Azure DevOps tooling contracts
- No EV2 workflows
- No Agency or internal MCP references
- No org-specific IDs, URLs, or tenant data

## Included Structure

- `AGENTS.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `.github/instructions/markdown.instructions.md`
- `.github/instructions/powershell.instructions.md`
- `.github/chatmodes/repo-expert.chatmode.md`
- `.github/prompts/example.prompt.md`
- `.github/skills/example-skill/SKILL.md`
- `.agent/instructions/collaboration-rules.instructions.md`
- `.agent/instructions/memory-bank.instructions.md`
- `.memory-bank/README.md`
- `.memory-bank/activeContext.md`
- `.memory-bank/learnings.md`
- `.memory-bank/userDirectives.md`
- `.specify/SPEC-KIT-README.md`
- `.specify/templates/` (spec, plan, tasks, checklist, constitution)
- `.specify/memory/constitution.md`
- `.specify/init-options.json`
- `.vscode/mcp.json`
- `.gitignore.additions`

## Quick Start

1. Copy all files in this folder into the target repository root, preserving paths.
2. Merge the entries in `.gitignore.additions` into your target repo `.gitignore`.
3. Replace placeholders in:
   - `AGENTS.md`
   - `.github/copilot-instructions.md`
4. Keep instruction files short and specific. Remove rules that do not fit your team workflow.

## Recommended Adoption Order

1. Add `.github/copilot-instructions.md` with real project conventions.
2. Add `AGENTS.md` startup rules.
3. Add `.memory-bank/` and memory-bank instructions.
4. Add collaboration rules.
5. Add language-specific instruction files.
6. Add the chat mode, example prompt, and example skill, then adapt them.
7. (Optional) Enable Spec Kit — see `.specify/SPEC-KIT-README.md`.
8. (Optional) Configure approved MCP servers in `.vscode/mcp.json`.

## Spec Kit

Spec Kit is the open-source spec-driven development workflow (Specify → Plan →
Tasks → Implement). The bundled `.specify/` folder includes the customizable
templates and config. To wire up the helper scripts and `/speckit-*` chat
commands, follow `.specify/SPEC-KIT-README.md` (recommended: the official
`specify init` initializer).

## Notes

- This template is intentionally minimal and portable.
- The quality of `.github/copilot-instructions.md` is the biggest factor in model quality.
- `.vscode/mcp.json` contains placeholders only — add solely MCP servers you are approved to use.
