"""Append-only JSONL provenance log per run."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


class ProvenanceLog:
    def __init__(self, runs_dir: str | Path, run_id: str) -> None:
        self.run_id = run_id
        self.dir = Path(runs_dir) / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "provenance.jsonl"

    def emit(self, kind: str, actor: str, **payload: Any) -> dict[str, Any]:
        evt = {
            "evtId": f"evt_{uuid.uuid4().hex[:12]}",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "runId": self.run_id,
            "kind": kind,
            "actor": actor,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")
        return evt


def new_run_id() -> str:
    return f"run_{time.strftime('%Y-%m-%d')}_{uuid.uuid4().hex[:6]}"


def runs_dir() -> Path:
    return Path(os.environ.get("CONCLAVE_RUNS_DIR", "../runs")).resolve()
