"""Tests for clearing out old runs.

This deletes files, so most of these are about what it must *not* touch.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from dogs_scraper.utils.housekeeping import prune_cache, prune_output, tidy

TODAY = date(2026, 9, 22)


def day(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture
def output(tmp_path):
    """A results directory spanning a month, plus things that are not ours."""
    d = tmp_path / "output"
    d.mkdir()
    for offset in (0, -1, -13, -14, -15, -30, 1):
        for name in (f"thedogs_{day(offset)}.json",
                     f"thedogs_{day(offset)}_runners.csv",
                     f"rbhq_{day(offset)}.json",
                     f"rbhq_{day(offset)}_runners.csv",
                     f"discrepancies_{day(offset)}.json"):
            (d / name).write_text("{}", encoding="utf-8")
    return d


def names(paths):
    return sorted(p.name for p in paths)


# -- what it removes -------------------------------------------------------
def test_keeps_the_retention_window(output):
    prune_output(output, keep_days=14, today=TODAY)
    days_left = sorted({n.split("_")[1].removesuffix(".json").removesuffix(".csv")
                        for n in (p.name for p in output.iterdir())})
    assert day(-15) not in days_left and day(-30) not in days_left
    assert day(-14) in days_left and day(-13) in days_left and day(0) in days_left


def test_zero_days_keeps_today_only(output):
    prune_output(output, keep_days=0, today=TODAY)
    left = {p.name.split("_")[1][:10] for p in output.iterdir()}
    assert left == {day(0), day(1)}, "today and the future survive"


def test_tomorrow_is_never_swept(output):
    """A card fetched ahead of time must not be deleted for being 'old'."""
    prune_output(output, keep_days=0, today=TODAY)
    assert (output / f"thedogs_{day(1)}.json").exists()


def test_negative_disables_it(output):
    before = names(output.iterdir())
    assert prune_output(output, keep_days=-1, today=TODAY) == []
    assert names(output.iterdir()) == before


# -- what it must not touch ------------------------------------------------
def test_leaves_everything_it_did_not_write(output):
    strangers = [
        ".gitkeep",
        "notes.json",
        "thedogs.json",                       # no date
        "thedogs_2026-09.json",               # partial date
        "backup_thedogs_2026-01-01.json",     # prefixed
        "thedogs_2026-01-01.json.bak",        # suffixed
        "thedogs_2026-01-01.txt",             # wrong extension
        "my_2026-01-01.json",                 # not one of ours
    ]
    for name in strangers:
        (output / name).write_text("keep me", encoding="utf-8")

    prune_output(output, keep_days=0, today=TODAY)

    for name in strangers:
        assert (output / name).exists(), f"{name} should not have been touched"


def test_does_not_recurse(output):
    """A subdirectory is somebody else's business."""
    nested = output / "archive"
    nested.mkdir()
    old = nested / f"thedogs_{day(-30)}.json"
    old.write_text("{}", encoding="utf-8")

    prune_output(output, keep_days=0, today=TODAY)
    assert old.exists()


def test_missing_directory_is_not_an_error(tmp_path):
    assert prune_output(tmp_path / "nope", keep_days=0, today=TODAY) == []
    assert prune_cache(tmp_path / "nope") == []


def test_dry_run_deletes_nothing(output):
    before = names(output.iterdir())
    would = prune_output(output, keep_days=0, today=TODAY, dry_run=True)

    assert would, "it should still report what it would remove"
    assert names(output.iterdir()) == before


# -- the page cache --------------------------------------------------------
def test_cache_is_aged_by_modification_time(tmp_path):
    import os
    import time

    cache = tmp_path / ".cache"
    (cache / "raw").mkdir(parents=True)

    fresh = cache / ("a" * 20 + ".html")
    stale = cache / ("b" * 20 + ".html")
    raw = cache / "raw" / "www.thedogs.com.au_racing_bulli.html"
    for path in (fresh, stale, raw):
        path.write_text("<html></html>", encoding="utf-8")

    long_ago = time.time() - (48 * 3600)
    os.utime(stale, (long_ago, long_ago))
    os.utime(raw, (long_ago, long_ago))

    removed = prune_cache(cache, max_age_hours=24)

    assert fresh.exists()
    assert not stale.exists()
    assert not raw.exists(), "raw dumps age out too"
    assert len(removed) == 2


def test_cache_leaves_other_files_alone(tmp_path):
    cache = tmp_path / ".cache"
    cache.mkdir()
    for name in ("notes.txt", "index.json", "not-a-hash.html"):
        (cache / name).write_text("keep", encoding="utf-8")

    import os
    import time
    long_ago = time.time() - (48 * 3600)
    for name in ("notes.txt", "index.json", "not-a-hash.html"):
        os.utime(cache / name, (long_ago, long_ago))

    prune_cache(cache, max_age_hours=1)
    for name in ("notes.txt", "index.json", "not-a-hash.html"):
        assert (cache / name).exists()


# -- the wrapper -----------------------------------------------------------
def test_tidy_uses_the_settings(tmp_path, output):
    from dogs_scraper.config import Settings

    settings = Settings.load(output_dir=output, cache_dir=tmp_path / ".cache",
                             output_retention_days=0)
    swept = tidy(settings, dry_run=True)
    assert swept["output"], "old results should be reported"
    assert swept["cache"] == []
