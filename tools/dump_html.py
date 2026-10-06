#!/usr/bin/env python
"""Save a real page to tests/fixtures/ so selectors can be tuned offline.

    python tools/dump_html.py https://www.thedogs.com.au/racing/goulburn/2026-08-28/1/red-tv-maiden
    python tools/dump_html.py --day 2026-08-28          # the day index
    python tools/dump_html.py --race goulburn 2026-08-28 1 red-tv-maiden

The saved file is what tests/test_parsers.py runs against, so once a fixture
is in place you can iterate on selectors without hitting the site again.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dogs_scraper.config import Settings           # noqa: E402
from dogs_scraper.fetcher import PageFetcher       # noqa: E402
from dogs_scraper.utils.logging import setup_logging  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main() -> int:
    p = argparse.ArgumentParser(description="Download a page and save it as a test fixture")
    p.add_argument("url", nargs="?", help="full URL to fetch")
    p.add_argument("--day", help="shortcut: fetch /racing/<date>")
    p.add_argument("--race", nargs=4, metavar=("TRACK", "DATE", "NO", "SLUG"),
                   help="shortcut: fetch a specific race page")
    p.add_argument("--name", help="fixture filename (default: derived from the URL)")
    args = p.parse_args()

    settings = Settings.load(use_cache=False)
    settings.ensure_dirs()
    setup_logging("INFO", settings.log_dir)

    if args.day:
        url = f"{settings.base_url}/racing/{args.day}"
    elif args.race:
        track, day, number, slug = args.race
        url = f"{settings.base_url}/racing/{track}/{day}/{number}/{slug}"
    elif args.url:
        url = args.url
    else:
        p.error("give a URL, --day, or --race")
        return 2

    page = PageFetcher(settings).get(url, allow_cache=False)
    html = getattr(page, "html_content", None) or getattr(page, "text", "") or ""
    if not html:
        print("No HTML came back.")
        return 1

    name = args.name or (re.sub(r"[^a-z0-9]+", "_", url.split("://")[-1].lower()).strip("_") + ".html")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / name
    path.write_text(html, encoding="utf-8")

    print(f"saved {len(html):,} bytes -> {path}")
    print("\nQuick structure check:")
    for selector in ("table", "tbody tr", "[data-testid]", "script#__NEXT_DATA__"):
        try:
            print(f"  {selector:<24} {len(page.css(selector))} match(es)")
        except Exception as exc:
            print(f"  {selector:<24} error: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
