"""Logging setup utilities."""

from __future__ import annotations

import logging
import sys


def setup_logging(verbose: bool = False) -> None:
    """Configure root logger for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger("git_diff_analyzer")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
