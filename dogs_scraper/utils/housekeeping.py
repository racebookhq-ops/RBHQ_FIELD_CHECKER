"""Clearing out old runs.

A daily run leaves five files behind and the page cache keeps every page it
fetched, so both grow without bound. This removes what has aged out.

It is deliberately timid, because it deletes things:

* **Only names this project writes.** Files are matched against an exact
  pattern - `thedogs_2026-09-22.json`, `rbhq_2026-09-22_runners.csv`,
  `discrepancies_2026-09-22.json` - not a glob. Anything else in the directory,
  including `.gitkeep` and anything you put there yourself, is left alone.
* **Only the directory it is given**, never a subdirectory of it, and never a
  parent.
* **Never today, and never the future.** Age comes from the racing date in the
  filename, not the modification time, so re-running an old day does not give
  it a stay of execution and tomorrow's card is never swept up.
* Every removal is logged, and `dry_run=True` reports without touching
  anything.
"""

from __future__ import annotations

import re
import time
from datetime import date as _date, timedelta
from pathlib import Path

from .dates import today_local
from .logging import get_logger

log = get_logger("housekeeping")

#: The files this project writes, and nothing else. The date is captured so a
#: file can be aged by the day it describes.
OUTPUT_FILE_RE = re.compile(
    r"^(?:thedogs|rbhq|discrepancies)_(\d{4}-\d{2}-\d{2})(?:_runners)?\.(?:json|csv)$"
)

#: Cached pages are named by a hash of their URL, so they can only be aged by
#: modification time.
CACHE_FILE_RE = re.compile(r"^[0-9a-f]{8,64}\.html$")


def prune_output(output_dir: str | Path, keep_days: int = 14, *,
                 today: _date | None = None, dry_run: bool = False) -> list[Path]:
    """Delete result files for racing days older than `keep_days`.

    `keep_days=0` keeps today only. A negative value disables pruning.
    """
    if keep_days is None or keep_days < 0:
        return []

    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return []

    cutoff = (today or today_local()) - timedelta(days=keep_days)
    removed: list[Path] = []

    for path in sorted(output_dir.iterdir()):
        if not path.is_file():
            continue
        match = OUTPUT_FILE_RE.match(path.name)
        if not match:
            continue                       # not ours - leave it alone
        try:
            file_day = _date.fromisoformat(match.group(1))
        except ValueError:
            continue
        if file_day >= cutoff:
            continue

        removed.append(path)
        if not dry_run:
            path.unlink(missing_ok=True)

    if removed:
        log.info("%s %d output file(s) older than %s",
                 "would remove" if dry_run else "removed", len(removed), cutoff)
        for path in removed:
            log.debug("  %s %s", "would remove" if dry_run else "removed", path.name)
    return removed


def prune_cache(cache_dir: str | Path, max_age_hours: int = 24, *,
                dry_run: bool = False) -> list[Path]:
    """Delete cached pages last written more than `max_age_hours` ago.

    A negative value disables pruning. The cache is only read within its much
    shorter TTL, so anything older is dead weight.
    """
    if max_age_hours is None or max_age_hours < 0:
        return []

    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return []

    cutoff = time.time() - (max_age_hours * 3600)
    removed: list[Path] = []

    # The cache proper, plus the raw/ dumps --save-raw-html leaves behind.
    for directory in (cache_dir, cache_dir / "raw"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix.lower() != ".html":
                continue
            # raw/ dumps are named after the URL, so only the hashed cache
            # files are pattern-checked; both are confined to .html here.
            if directory == cache_dir and not CACHE_FILE_RE.match(path.name):
                continue
            try:
                if path.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue

            removed.append(path)
            if not dry_run:
                path.unlink(missing_ok=True)

    if removed:
        log.info("%s %d cached page(s) older than %dh",
                 "would remove" if dry_run else "removed", len(removed), max_age_hours)
    return removed


def tidy(settings, *, dry_run: bool = False) -> dict[str, list[Path]]:
    """Run both sweeps using the retention values on `settings`."""
    return {
        "output": prune_output(settings.output_dir, settings.output_retention_days,
                               dry_run=dry_run),
        "cache": prune_cache(settings.cache_dir, settings.cache_retention_hours,
                             dry_run=dry_run),
    }
