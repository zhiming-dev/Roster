# CLAUDE.md

> Canonical agent instructions live in [.github/copilot-instructions.md](.github/copilot-instructions.md)
> and [AGENTS.md](AGENTS.md). This file exists so Claude Code finds the right entry point.

## Repository

- Name: Roster — human-in-the-loop, hierarchical multi-agent framework
- Default branch: main
- Languages: Markdown (agents/skills/specs), Python 3.10+ (runtime)
- Key directories: `planner-agent/`, `coder-agent/`, `qa-agent/`, `reviewer-agent/`,
  `researcher-agent/`, `e2e-agent/`, `shared/`, `runtime/`, `runs/`
- Test framework: none yet — JSON artifacts are validated against `shared/schemas/*.schema.json`

## Run the runtime

```powershell
cd runtime
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m roster          # serves http://localhost:8765/
```

## See also

- [.github/copilot-instructions.md](.github/copilot-instructions.md)
- [AGENTS.md](AGENTS.md)
