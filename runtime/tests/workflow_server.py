"""Disposable backend for the browser workflow test. No external model calls."""

import os
import tempfile
from pathlib import Path

import uvicorn
import yaml

from .conftest import init_git_repo
from .test_workflow import Scripted


class DemoProvider(Scripted):
    async def health(self):
        return {"ok": True, "model_present": True}


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = init_git_repo(root / "target")
        repo = Path(__file__).resolve().parents[2]
        config = root / "config.yaml"
        config.write_text(yaml.safe_dump({
            "search": {"enabled": False},
            "workspace": {"target_repo": str(target), "worktrees_root": str(root / "trees")},
            "defaults": {"provider": "ollama", "model": "scripted", "endpoint": "http://localhost:1"},
            "agents": {
                role: {"role": role, "agent_file": str(repo / f"{role}-agent" / f"{role}.agent.md"),
                       "tools": ["read", "edit", "execute"] if role == "coder" else []}
                for role in ["planner", "coder", "reviewer"]
            },
        }))
        os.environ.update(ROSTER_CONFIG=str(config), ROSTER_RUNS_DIR=str(root / "runs"), ROSTER_DB_PATH=str(root / "data.db"))
        from roster import server
        from roster.orchestrator import Run
        run = Run(config)
        run.planner.provider = DemoProvider(["Update VALUE in src/app.py from 1 to 2. Keep the change scoped to that file."])
        run.subagents["coder"].provider = DemoProvider(["EDIT: src/app.py\n```\nVALUE = 2\n```", "Updated VALUE in src/app.py"])
        run.subagents["reviewer"].provider = DemoProvider(["The diff changes only VALUE, matching the request.\nREVIEW: PASS"])
        server._run = run
        uvicorn.run(server.app, host="127.0.0.1", port=8876)


if __name__ == "__main__":
    main()
