"""Command line interface.

    python -m rbhq_scraper --date today
    python -m rbhq_scraper --date 2026-09-22 --state SA WA
    python -m rbhq_scraper --file response.json          # replay a saved one
    python -m rbhq_scraper --harness --date today        # harness meetings instead

The endpoint and credentials come from the `rbhq:` block in config.yaml and an
environment variable - see rbhq_scraper/config.py. Writes the same JSON and CSV
shape the dogs scraper writes, under an `rbhq_` prefix, so the two cards sit
side by side in `output/`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dogs_scraper.config import Settings
from dogs_scraper.exporters import write_csv, write_json
from dogs_scraper.models import parse_date
from dogs_scraper.utils.housekeeping import tidy
from dogs_scraper.utils.logging import setup_logging

from .client import FeedError, fetch_day, load_file, save_response
from .config import HARNESS_CODE, FeedConfig
from .mapper import DEFAULT_COUNTRIES, build_card

OUTPUT_PREFIX = "rbhq"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rbhq_scraper",
        description="Fetch the RBHQ greyhound feed and map it onto the same card "
                    "shape as the thedogs.com.au scraper",
    )
    p.add_argument("--date", default="today",
                   help="today | tomorrow | yesterday | YYYY-MM-DD  (default: today)")

    source = p.add_argument_group("source")
    source.add_argument("--file", default=None,
                        help="replay a saved response instead of calling the API")
    source.add_argument("--url", default=None,
                        help="override rbhq.base_url for this run")
    source.add_argument("--save-response", default=None, metavar="PATH",
                        help="write the raw payload out, so this run can be replayed")
    source.add_argument("--show-endpoint", action="store_true",
                        help="print the endpoint that would be called, and exit")

    scope = p.add_argument_group("scope")
    scope.add_argument("--harness", action="store_true",
                       help="harness (race type H) instead of greyhounds; writes "
                            "data/harness/{date}/rbhq_fields.{csv,json}. Mapping is "
                            "unverified - see rbhq_scraper/harness_mapper.py")
    scope.add_argument("--all-days", action="store_true",
                       help="keep every racing day the payload contains")
    scope.add_argument("--state", nargs="*", default=None, metavar="CODE",
                       help="limit to states, e.g. --state NSW VIC")
    scope.add_argument("--track", nargs="*", default=None, metavar="SLUG",
                       help="limit to track slugs, e.g. --track angle-park")
    scope.add_argument("--country", nargs="*", default=None, metavar="CODE",
                       help=f"countries to keep (default: {' '.join(DEFAULT_COUNTRIES)})")

    out = p.add_argument_group("output")
    out.add_argument("--output-dir", default=None, help="where to write results")
    out.add_argument("--config", default=None, help="path to a config.yaml")
    out.add_argument("--json-only", action="store_true")
    out.add_argument("--csv-only", action="store_true")
    out.add_argument("--log-level", default=None,
                     choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    house = p.add_argument_group("housekeeping")
    house.add_argument("--keep-days", type=int, default=None, metavar="N",
                       help="racing days of results to keep (default: 14; "
                            "0 = today only, -1 = keep everything)")
    house.add_argument("--no-prune", action="store_true",
                       help="leave old results and cached pages alone")
    house.add_argument("--prune-dry-run", action="store_true",
                       help="report what would be deleted, delete nothing")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)

    settings = Settings.load(
        args.config,
        states=args.state,
        tracks=args.track,
        output_dir=args.output_dir,
        log_level=args.log_level,
        output_retention_days=args.keep_days,
        write_csv=False if args.json_only else None,
        write_json=False if args.csv_only else None,
    )
    settings.ensure_dirs()
    setup_logging(settings.log_level, settings.log_dir)

    feed = FeedConfig.load(args.config, base_url=args.url,
                           race_types=[HARNESS_CODE] if args.harness else None)
    day = parse_date(args.date)

    if args.show_endpoint:
        import json as _json
        print()
        print(f"  {feed.method}  {feed.url_for(day)}")
        print(f"  body      {_json.dumps(feed.body_for(day))}")
        if feed.query_for(day):
            print(f"  query     {feed.query_for(day)}")
        print(f"  auth      {feed.describe().split('auth: ')[-1]}")
        print()
        return 0 if feed.configured else 2

    try:
        payload = load_file(args.file) if args.file else fetch_day(day, feed)
    except FeedError as exc:
        print(f"\n  {exc}\n")
        return 2

    if args.save_response:
        save_response(payload, args.save_response)

    # A saved file may hold days other than the one asked for; a live call is
    # already scoped to the day, so filtering it is a no-op either way.
    filter_day = None if args.all_days else day

    scope = dict(
        countries=args.country if args.country is not None else DEFAULT_COUNTRIES,
        states=settings.states,
        tracks=settings.tracks,
    )

    written = []
    if args.harness:
        from harness_scraper.config import Settings as HarnessSettings
        from harness_scraper.exporters import write_csv as h_csv, write_json as h_json
        from .harness_mapper import build_harness_card

        card = build_harness_card(payload, filter_day, **scope)
        root = HarnessSettings.load(args.config, data_dir=args.output_dir and Path(args.output_dir)).output_root
        if settings.write_json:
            written.append(h_json(card, root, settings.pretty_json, name="rbhq_fields"))
        if settings.write_csv:
            written.append(h_csv(card, root, name="rbhq_fields"))
    else:
        card = build_card(payload, filter_day, **scope)
        if settings.write_json:
            written.append(write_json(card, settings.output_dir, settings.pretty_json,
                                      prefix=OUTPUT_PREFIX))
        if settings.write_csv:
            written.append(write_csv(card, settings.output_dir, prefix=OUTPUT_PREFIX))

    print()
    print(f"  date      {card.meeting_date or '(all days in payload)'}")
    print(f"  meetings  {len(card.meetings)}")
    print(f"  races     {card.total_races}")
    print(f"  runners   {card.total_runners}")
    if card.errors:
        print(f"  errors    {len(card.errors)}  (see the JSON 'errors' array)")
    for path in written:
        print(f"  ->        {path}")
    print()

    if not card.total_runners:
        print("No runners were mapped. The feed answered, but nothing matched the")
        print("filters - check --date and --country against what came back:")
        print("  --save-response raw.json   keeps the payload so you can look")
        print("  --all-days --country AU GB widens the net")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
