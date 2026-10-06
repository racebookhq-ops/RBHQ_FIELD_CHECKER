#!/usr/bin/env python
"""Save real harness.org.au pages and the API JSON they load as test fixtures.

    python tools/dump_harness.py                       # today, first non-trial meeting, race 1
    python tools/dump_harness.py --date 2026-10-06
    python tools/dump_harness.py --date 2026-10-06 --meeting AP061026 --race-no 4
    python tools/dump_harness.py --headful

Writes to tests/fixtures/harness/:

    index.html          the /racing/fields?date= page (rendered)
    index_api.json      the /racing/fields?date= JSON the page requested
    meeting_api.json    /racing/{meetingCode}/        - every race of the meeting
    race_page.html      one race page (rendered) - input for the text fallback
    race_api.json       /racing/{meetingCode}/{raceId} - that one race
    fixture_meta.json   what was captured, and when

tests/test_harness_*.py run against these files and skip when they are absent.
Run this on a machine that can reach the site, then commit the fixtures.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dogs_scraper.models import parse_date                       # noqa: E402
from dogs_scraper.utils.logging import setup_logging              # noqa: E402
from harness_scraper.browser import HarnessBrowser                # noqa: E402
from harness_scraper.config import Settings                       # noqa: E402
from harness_scraper.discovery import (merge_discovery, parse_index_json,  # noqa: E402
                                       parse_index_links)

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "harness"


def _write_json(name: str, data) -> None:
    (FIXTURES / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  saved {name}")


def main() -> int:
    p = argparse.ArgumentParser(description="Capture harness.org.au fixtures")
    p.add_argument("--date", default="today")
    p.add_argument("--meeting", help="meeting code, e.g. AP061026 (default: first non-trial meeting)")
    p.add_argument("--race-no", type=int, default=1, help="race number to capture as the race page (default 1)")
    p.add_argument("--headful", action="store_true")
    args = p.parse_args()

    settings = Settings.load(headless=False if args.headful else None)
    settings.ensure_dirs()
    setup_logging("INFO", settings.log_dir)
    day = parse_date(args.date).isoformat()
    FIXTURES.mkdir(parents=True, exist_ok=True)

    with HarnessBrowser(settings) as browser:
        index = browser.fetch(f"{settings.base_url}/racing/fields?date={day}", expect=r"/racing/fields\?date=")
        (FIXTURES / "index.html").write_text(index.html, encoding="utf-8")
        print("  saved index.html")
        index_json = index.find(r"/racing/fields\?date=")
        if index_json is None:
            print("The page did not request /racing/fields?date= - no index_api.json captured.")
        else:
            _write_json("index_api.json", index_json)

        meetings = merge_discovery(parse_index_links(index.html, day, settings.base_url),
                                   parse_index_json(index_json, settings.base_url))
        if not meetings:
            print(f"No meetings found for {day}.")
            return 1
        dm = next((m for m in meetings if m.meeting_code == args.meeting), None) if args.meeting else meetings[0]
        if dm is None:
            print(f"Meeting {args.meeting} not on the index. Available: {[m.meeting_code for m in meetings]}")
            return 1
        ir = next((r for r in dm.races if r.race_no == args.race_no), None)
        if ir is None:
            print(f"Race {args.race_no} not found for {dm.meeting_code}: {[r.race_no for r in dm.races]}")
            return 1

        mtg = browser.fetch(dm.url, expect=rf"/racing/{dm.meeting_code}/?$")
        mtg_json = mtg.find(rf"/racing/{dm.meeting_code}/?$")
        if mtg_json is None:
            print("Meeting API response was not captured.")
        else:
            _write_json("meeting_api.json", mtg_json)

        race_url = (f"{settings.base_url}/racing/{day}/{dm.track_slug}/{dm.meeting_code}"
                    f"/meeting/{ir.race_id}/{ir.race_no}/fields")
        race = browser.fetch(race_url, expect=rf"/racing/{dm.meeting_code}/{ir.race_id}$")
        (FIXTURES / "race_page.html").write_text(race.html, encoding="utf-8")
        print("  saved race_page.html")
        race_json = race.find(rf"/racing/{dm.meeting_code}/{ir.race_id}$")
        if race_json is None:
            print("Race API response was not captured.")
        else:
            _write_json("race_api.json", race_json)

    _write_json("fixture_meta.json", {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "date": day,
        "meeting_code": dm.meeting_code,
        "race_id": ir.race_id,
        "race_no": ir.race_no,
        "race_url": race_url,
        "index_meetings": [m.meeting_code for m in meetings],
        "have": {"index_api": index_json is not None, "meeting_api": mtg_json is not None,
                 "race_api": race_json is not None},
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
