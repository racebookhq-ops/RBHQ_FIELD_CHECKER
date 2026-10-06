"""Command line interface.

    scrape    pull a day's harness fields from harness.org.au -> JSON + CSV

    python -m harness_scraper scrape --date 2026-10-06
    python -m harness_scraper scrape --state NSW,VIC --include-trials
    python -m harness_scraper scrape --date 2026-10-06 --from-raw    # no network

Running with no subcommand does `scrape`.
"""

from __future__ import annotations

import argparse
import sys

from dogs_scraper.models import parse_date
from dogs_scraper.utils.logging import setup_logging

from .config import Settings
from .exporters import write_csv, write_json
from .scraper import HarnessScraper


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness_scraper",
        description="Harness fields: scrape a day's meetings, races and runners from harness.org.au",
    )
    subs = p.add_subparsers(dest="command")

    scrape = subs.add_parser("scrape", help="scrape a day's fields from harness.org.au")
    scrape.add_argument("--date", default="today",
                        help="today | tomorrow | yesterday | YYYY-MM-DD  (default: today)")
    scrape.add_argument("--include-trials", action="store_true",
                        help="also scrape trial meetings (hidden on the site by default)")
    scrape.add_argument("--state", nargs="*", default=None, metavar="CODE",
                        help="limit to states, e.g. --state NSW,VIC  or  --state NSW VIC")
    scrape.add_argument("--headful", action="store_true",
                        help="show the browser window (debugging)")
    scrape.add_argument("--from-raw", action="store_true",
                        help="rebuild from data/raw/{date}/*.json instead of fetching")
    scrape.add_argument("--data-dir", default=None, help="where data/ lives (default: ./data)")
    scrape.add_argument("--config", default=None, help="path to a config.yaml")
    scrape.add_argument("--fetcher", choices=["stealthy", "dynamic"], default=None)
    scrape.add_argument("--json-only", action="store_true")
    scrape.add_argument("--csv-only", action="store_true")
    scrape.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def _states(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    return [s.strip().upper() for v in values for s in v.split(",") if s.strip()]


def cmd_scrape(args, settings: Settings) -> int:
    scraper = HarnessScraper(settings)
    day = parse_date(args.date)
    card = scraper.scrape_from_raw(day) if args.from_raw else scraper.scrape_day(day)

    written = []
    if settings.write_json:
        written.append(write_json(card, settings.output_root, settings.pretty_json))
    if settings.write_csv:
        written.append(write_csv(card, settings.output_root))

    print()
    print(f"  date      {card.meeting_date}")
    print(f"  meetings  {len(card.meetings)}")
    print(f"  races     {card.total_races}")
    print(f"  runners   {card.total_runners}")
    if card.errors:
        print(f"  errors    {len(card.errors)}  (see the JSON 'errors' array)")
    for path in written:
        print(f"  ->        {path}")
    print()

    if not card.total_runners:
        print("No runners were parsed. Re-run with --headful --log-level DEBUG to watch the browser.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv.insert(0, "scrape")

    args = build_parser().parse_args(argv)

    settings = Settings.load(
        args.config,
        states=_states(args.state),
        include_trials=True if args.include_trials else None,
        headless=False if args.headful else None,
        data_dir=args.data_dir,
        fetcher=args.fetcher,
        log_level=args.log_level,
        write_csv=False if args.json_only else None,
        write_json=False if args.csv_only else None,
    )
    settings.ensure_dirs()
    setup_logging(settings.log_level, settings.log_dir)

    return cmd_scrape(args, settings)


if __name__ == "__main__":
    sys.exit(main())
