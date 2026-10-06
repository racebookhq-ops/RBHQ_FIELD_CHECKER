"""Command line interface.

    python -m field_compare --date today
    python -m field_compare --date today --strict
    python -m field_compare --harness --date today      # harness vs harness.org.au
    python -m field_compare --reference-file output/thedogs_2026-09-22.json \
                            --ours-file response.json

Both sides are fetched live by default - thedogs.com.au is scraped, and the
RBHQ feed is called. `--reference-file` and `--ours-file` replay saved cards
instead, which makes debugging a report free.

Exit code is **1 when anything critical is found**, so a scheduled run shows up
as a failure rather than passing quietly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dogs_scraper.config import Settings
from dogs_scraper.models import card_from_dict, parse_date
from dogs_scraper.utils.housekeeping import tidy
from dogs_scraper.utils.logging import setup_logging
from rbhq_scraper import FeedConfig, scrape, scrape_file

from .matcher import DEFAULT_ALIASES, load_aliases
from .report import print_report, write_report
from .rules import compare_cards


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="field_compare",
        description="Check the RBHQ fields against the fields published on "
                    "thedogs.com.au, box by box",
    )
    p.add_argument("--harness", action="store_true",
                   help="compare the RBHQ harness fields against harness.org.au "
                        "instead of greyhounds (see field_compare/harness.py)")
    p.add_argument("--ours-file", default=None,
                   help="replay a saved RBHQ response instead of calling the API")
    p.add_argument("--reference-file", default=None,
                   help="a saved thedogs card instead of scraping one")
    p.add_argument("--url", default=None,
                   help="override rbhq.base_url for this run")
    p.add_argument("--date", default="today",
                   help="today | tomorrow | yesterday | YYYY-MM-DD")
    p.add_argument("--strict", action="store_true",
                   help="also compare trainer (noisier)")
    p.add_argument("--aliases", default=None,
                   help=f"track alias file (default: {DEFAULT_ALIASES.name})")
    p.add_argument("--state", nargs="*", default=None, metavar="CODE")
    p.add_argument("--track", nargs="*", default=None, metavar="SLUG")
    p.add_argument("--output-dir", default=None)
    p.add_argument("--config", default=None)
    p.add_argument("--save-cards", action="store_true",
                   help="also write both source cards alongside the report")
    house = p.add_argument_group("housekeeping")
    house.add_argument("--keep-days", type=int, default=None, metavar="N",
                       help="racing days of results to keep (default: 14; "
                            "0 = today only, -1 = keep everything)")
    house.add_argument("--no-prune", action="store_true",
                       help="leave old results and cached pages alone")
    house.add_argument("--prune-dry-run", action="store_true",
                       help="report what would be deleted, delete nothing")
    p.add_argument("--log-level", default=None,
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)

    if args.harness:
        from .harness_cli import run
        return run(args)

    settings = Settings.load(
        args.config,
        states=args.state,
        tracks=args.track,
        output_dir=args.output_dir,
        log_level=args.log_level,
        output_retention_days=args.keep_days,
    )
    settings.ensure_dirs()
    setup_logging(settings.log_level, settings.log_dir)

    day = parse_date(args.date)

    # -- our field ----------------------------------------------------------
    # Fetched first, deliberately: it is one request, while scraping the
    # reference is a few hundred. A bad key or a changed endpoint should fail
    # in a second rather than after several minutes of scraping.
    try:
        if args.ours_file:
            ours = scrape_file(args.ours_file, day,
                               states=settings.states, tracks=settings.tracks)
        else:
            ours = scrape(day, FeedConfig.load(args.config, base_url=args.url),
                          states=settings.states, tracks=settings.tracks)
    except Exception as exc:                     # noqa: BLE001 - reported, not raised
        print(f"\n  Could not read our fields: {exc}\n")
        return 2

    # -- the published field ------------------------------------------------
    if args.reference_file:
        reference = card_from_dict(
            json.loads(Path(args.reference_file).read_text(encoding="utf-8")))
    else:
        from dogs_scraper.scraper import DogsScraper
        reference = DogsScraper(settings).scrape_day(day)

    report = compare_cards(reference, ours, strict=args.strict,
                           aliases=load_aliases(args.aliases))

    path = write_report(report, settings.output_dir, settings.pretty_json)
    print_report(report)
    print(f"  -> {path}")

    if args.save_cards:
        from dogs_scraper.exporters import write_json
        print(f"  -> {write_json(reference, settings.output_dir, settings.pretty_json)}")
        print(f"  -> {write_json(ours, settings.output_dir, settings.pretty_json, prefix='rbhq')}")


    # -- housekeeping -------------------------------------------------------
    # Last, so a failed run never takes the previous good result with it.
    if not args.no_prune:
        swept = tidy(settings, dry_run=args.prune_dry_run)
        gone = swept["output"] + swept["cache"]
        if gone:
            verb = "would delete" if args.prune_dry_run else "deleted"
            print(f"  {verb}  {len(swept['output'])} old result file(s), "
                  f"{len(swept['cache'])} cached page(s)")
            for path in swept["output"]:
                print(f"             {path.name}")
            print()
    # Non-zero when something a punter could act on is wrong.
    return 1 if report.critical else 0


if __name__ == "__main__":
    sys.exit(main())
