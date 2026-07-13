"""Build and persist a schema-valid TaskResult plus its diff artifact (spec 004, T014).

After a tool-using specialist finishes, the runtime captures the cumulative change set of its
worktree as ``runs/<runId>/artifacts/<taskId>/diff.patch`` and a ``TaskResult`` JSON at
``runs/<runId>/results/<taskId>.json`` that conforms to
``shared/schemas/task-result.schema.json`` (constitution VI). Plumbing only — no git here; the
patch is computed by the executor (``ToolExecutor.full_diff``) and passed in.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .diffutil import summarize_diff


def new_task_id() -> str:
    return f"task_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run_dir(runs_dir: str | Path, run_id: str) -> Path:
    return Path(runs_dir) / run_id


def write_diff_artifact(runs_dir: str | Path, run_id: str, task_id: str, patch: str) -> str:
    """Write the diff under ``artifacts/<taskId>/diff.patch``; return the run-relative path."""
    rel = f"artifacts/{task_id}/diff.patch"
    path = _run_dir(runs_dir, run_id) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(patch.encode("utf-8"))  # verbatim LF, no CRLF translation
    return rel


def build_task_result(
    *,
    task_id: str,
    run_id: str,
    completed_by: str,
    summary: str,
    patch: str,
    status: str = "success",
) -> dict[str, Any]:
    """Build a TaskResult dict conforming to ``task-result.schema.json``.

    A non-empty ``patch`` yields a ``kind:"diff"`` artifact entry pointing at the written
    ``diff.patch``; an empty change set omits the artifact but is still valid.
    """
    files = summarize_diff(patch)
    additions = sum(f.additions for f in files)
    deletions = sum(f.deletions for f in files)
    result: dict[str, Any] = {
        "taskId": task_id,
        "runId": run_id,
        "status": status,
        "completedBy": completed_by,
        "completedAt": _now_iso(),
        "summary": summary,
        "metrics": {
            "filesChanged": len(files),
            "additions": additions,
            "deletions": deletions,
        },
    }
    if files:
        result["artifacts"] = [
            {
                "path": f"artifacts/{task_id}/diff.patch",
                "kind": "diff",
                "summary": f"{len(files)} file(s) changed, +{additions}/-{deletions}",
            }
        ]
        result["evidence"] = f"Change set captured in artifacts/{task_id}/diff.patch."
    return result


def write_task_result(runs_dir: str | Path, run_id: str, result: dict[str, Any]) -> str:
    """Write the TaskResult under ``results/<taskId>.json``; return the run-relative path."""
    rel = f"results/{result['taskId']}.json"
    path = _run_dir(runs_dir, run_id) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rel
