"""Console + rotating file logging, configured once from the CLI."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)-22s  %(message)s"
_DATEFMT = "%H:%M:%S"


#: Every package that logs through here. Each gets the same handlers, so a
#: sibling scraper's output is configured by the same one call.
ROOTS = ("dogs_scraper", "rbhq_scraper", "harness_scraper")


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> logging.Logger:
    handlers: list[logging.Handler] = []

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
    handlers.append(console)

    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "scraper.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(_FORMAT, "%Y-%m-%d %H:%M:%S"))
        handlers.append(file_handler)

    first = None
    for name in ROOTS:
        root = logging.getLogger(name)
        root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
        root.handlers.clear()
        root.propagate = False
        for handler in handlers:
            root.addHandler(handler)
        first = first or root

    return first


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"dogs_scraper.{name}")
