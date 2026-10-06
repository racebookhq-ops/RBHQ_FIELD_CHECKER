"""Command line interface.

    scrape    pull a day's fields from thedogs.com.au -> JSON + CSV

    python -m dogs_scraper scrape --date today

Running with no subcommand does `scrape`, so older invocations still work.
"""

from __future__ import annotations

import argparse
import sys

from .config import Settings
from .exporters import write_csv, write_json
from .models import parse_date
from .scraper import DogsScraper
from .utils.housekeeping import tidy
from .utils.logging import setup_logging


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------
def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--date", default="today",
                   help="today | tomorrow | yesterday | YYYY-MM-DD  (default: today)")
    p.add_argument("--output-dir", default=None, help="where to write results")
    p.add_argument("--config", default=None, help="path to a config.yaml")
    p.add_argument("--no-cache", action="store_true", help="ignore the local page cache")
    p.add_argument("--log-level", default=None,
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dogs_scraper",
        description="Greyhound fields: scrape a day's meetings, races and runners "
                    "from thedogs.com.au",
    )
    subs = p.add_subparsers(dest="command")

    # -- scrape ------------------------------------------------------------
    scrape = subs.add_parser("scrape", help="scrape a day's fields from thedogs.com.au")
    _common(scrape)
    scrape.add_argument("--state", nargs="*", default=None, metavar="CODE",
                        help="limit to states, e.g. --state NSW VIC")
    scrape.add_argument("--track", nargs="*", default=None, metavar="SLUG",
                        help="limit to track slugs, e.g. --track goulburn wagga")
    scrape.add_argument("--fetcher", choices=["fetcher", "stealthy", "dynamic"], default=None)
    scrape.add_argument("--extraction-mode", choices=["auto", "json", "html"], default=None)
    scrape.add_argument("--json-only", action="store_true")
    scrape.add_argument("--csv-only", action="store_true")
    scrape.add_argument("--save-raw-html", action="store_true",
                        help="dump every fetched page to .cache/raw for selector work")
    scrape.add_argument("--delay", type=float, default=None,
                        help="seconds between requests (default: 1.0)")
    house = p.add_argument_group("housekeeping")
    house.add_argument("--keep-days", type=int, default=None, metavar="N",
                       help="racing days of results to keep (default: 14; "
                            "0 = today only, -1 = keep everything)")
    house.add_argument("--no-prune", action="store_true",
                       help="leave old results and cached pages alone")
    house.add_argument("--prune-dry-run", action="store_true",
                       help="report what would be deleted, delete nothing")
    return p


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_scrape(args, settings: Settings) -> int:
    card = DogsScraper(settings).scrape_day(parse_date(args.date))

    written = []
    if settings.write_json:
        written.append(write_json(card, settings.output_dir, settings.pretty_json))
    if settings.write_csv:
        written.append(write_csv(card, settings.output_dir))

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
        print("No runners were parsed. Re-run with --save-raw-html --log-level DEBUG,")
        print("then use tools/dump_html.py and update dogs_scraper/parsers/selectors.py.")
        return 1
    return 0


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv.insert(0, "scrape")            # backwards compatible default

    args = build_parser().parse_args(argv)

    settings = Settings.load(
        args.config,
        states=getattr(args, "state", None),
        tracks=getattr(args, "track", None),
        output_dir=args.output_dir,
        fetcher=getattr(args, "fetcher", None),
        extraction_mode=getattr(args, "extraction_mode", None),
        delay_between_requests=getattr(args, "delay", None),
        log_level=args.log_level,
        output_retention_days=args.keep_days,
        save_raw_html=True if getattr(args, "save_raw_html", False) else None,
        use_cache=False if args.no_cache else None,
        write_csv=False if getattr(args, "json_only", False) else None,
        write_json=False if getattr(args, "csv_only", False) else None,
    )
    settings.ensure_dirs()
    setup_logging(settings.log_level, settings.log_dir)

    return cmd_scrape(args, settings)


if __name__ == "__main__":
    sys.exit(main())
