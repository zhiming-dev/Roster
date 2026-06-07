"""Entry point: `python -m conclave` starts the FastAPI server."""

from __future__ import annotations

import argparse
import os

import uvicorn

from .logging_setup import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(prog="conclave")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--config",
        default=os.environ.get("CONCLAVE_CONFIG", "agents.config.yaml"),
        help="Path to agents.config.yaml",
    )
    parser.add_argument(
        "--runs-dir",
        default=os.environ.get("CONCLAVE_RUNS_DIR", "../runs"),
        help="Directory where run artifacts (provenance.jsonl, etc.) are written",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("CONCLAVE_LOG_LEVEL", "INFO"),
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    os.environ["CONCLAVE_CONFIG"] = os.path.abspath(args.config)
    os.environ["CONCLAVE_RUNS_DIR"] = os.path.abspath(args.runs_dir)

    uvicorn.run(
        "conclave.server:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
