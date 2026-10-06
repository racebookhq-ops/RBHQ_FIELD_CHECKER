"""Loggers for this package.

Handlers are installed by `dogs_scraper.utils.logging.setup_logging`, which
configures every root named in its ROOTS tuple - this one included.
"""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"rbhq_scraper.{name}")
