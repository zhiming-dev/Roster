"""Logging configuration for the runtime."""

from __future__ import annotations

import logging
import os


def setup_logging(level: str | int | None = None) -> logging.Logger:
    resolved = level or os.environ.get("CONCLAVE_LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=resolved,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Tame noisy third-party loggers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return logging.getLogger("conclave")
