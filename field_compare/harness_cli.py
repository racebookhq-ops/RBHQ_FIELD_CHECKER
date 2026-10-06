"""`python -m field_compare --harness` - RBHQ harness fields vs harness.org.au.

    python -m field_compare --harness --date today
    python -m field_compare --harness --date 2026-10-06 --state NSW,VIC
    python -m field_compare --harness --reference-file data/harness/2026-10-06/fields.json \
                            --ours-file raw_h.json

Both sides are fetched live by default: the RBHQ feed first (one request, so a bad
key fails fast), then harness.org.au in a browser. `--reference-file` replays a
saved harness fields.json; `--ours-file` replays a saved RBHQ response.

Writes data/harness/{date}/discrepancies.json. Exit code 1 when anything critical
is found.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dogs_scraper.models import parse_date
from dogs_scraper.utils.logging import setup_logging
from harness_scraper.config import Settings
from harness_scraper.exporters import write_json
from harness_scraper.models import card_from_dict
from harness_scraper.scraper import HarnessScraper
from rbhq_scraper.client import load_file
from rbhq_scraper.config import HARNESS_CODE, FeedConfig
from rbhq_scraper.harness_mapper import build_harness_card
from rbhq_scraper import scrape_harness

from .harness import DEFAULT_HARNESS_ALIASES, compare_harness
from .matcher import load_aliases
from .report import print_report, write_report


def run(args) -> int:
    states = [s.strip().upper() for v in (args.state or []) for s in v.split(",") if s.strip()]
    settings = Settings.load(args.config, states=states or None,
                             data_dir=args.output_dir, log_level=args.log_level)
    settings.ensure_dirs()
    setup_logging(settings.log_level, settings.log_dir)
    day = parse_date(args.date)

    # -- ours: the RBHQ feed ------------------------------------------------
    try:
        if args.ours_file:
            ours = build_harness_card(load_file(args.ours_file), day, states=settings.states)
        else:
            feed = FeedConfig.load(args.config, base_url=args.url, race_types=[HARNESS_CODE])
            ours = scrape_harness(day, feed, states=settings.states)
    except Exception as exc:                     # noqa: BLE001 - reported, not raised
        print(f"\n  Could not read our fields: {exc}\n")
        return 2

    if not ours.meetings:
        # Nothing on our side means the feed gave us no harness at all, not that
        # every meeting is missing - a report of six "missing" meetings would be
        # a false alarm, so stop here and say what happened.
        print()
        print("  Our side has no harness meetings for this date, so there is nothing to compare.")
        print("  The RBHQ feed returned no harness (race type H) meetings - the request succeeded,")
        print("  but the response held none. Check, with --save-response, which meeting types the")
        print("  feed returns for this key (a probe on 6 Oct 2026 saw only G / greyhounds), or")
        print("  whether harness comes from another endpoint or needs another race-type code.")
        for e in ours.errors:
            print(f"  feed error: {e}")
        print("  No report was written.")
        print()
        return 2

    # -- the published field ------------------------------------------------
    if args.reference_file:
        reference = card_from_dict(json.loads(Path(args.reference_file).read_text(encoding="utf-8")))
    else:
        reference = HarnessScraper(settings).scrape_day(day)

    if reference.errors:
        print(f"\n  Note: harness.org.au scrape reported {len(reference.errors)} error(s); "
              f"missing races below may be a scrape problem, not a feed problem.")

    aliases = load_aliases(args.aliases or DEFAULT_HARNESS_ALIASES)
    report = compare_harness(reference, ours, aliases=aliases)

    root = settings.output_root
    path = write_report(report, root / report.meeting_date, settings.pretty_json,
                        filename="discrepancies.json")
    print_report(report)
    print(f"  -> {path}")

    if args.save_cards:
        print(f"  -> {write_json(reference, root, settings.pretty_json)}")
        print(f"  -> {write_json(ours, root, settings.pretty_json, name='rbhq_fields')}")
    print()
    return 1 if report.critical else 0


if __name__ == "__main__":                       # pragma: no cover
    sys.exit(1)
