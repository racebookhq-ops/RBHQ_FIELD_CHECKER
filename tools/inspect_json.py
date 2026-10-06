#!/usr/bin/env python
"""Map an embedded JSON payload so the parser can read it directly.

Run this once against a race page. If the site ships its card as JSON, this
prints where the races/runners live so you can write a precise json parser
instead of relying on CSS selectors.

    python tools/inspect_json.py https://www.thedogs.com.au/racing/goulburn/2026-08-28/1/red-tv-maiden
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dogs_scraper.config import Settings                        # noqa: E402
from dogs_scraper.discovery import extract_embedded_json, find_collections  # noqa: E402
from dogs_scraper.fetcher import PageFetcher                    # noqa: E402
from dogs_scraper.utils.logging import setup_logging            # noqa: E402

INTERESTING = ("races", "race", "runners", "runner", "entries", "dogs",
               "meetings", "meeting", "fields", "form")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    settings = Settings.load(use_cache=False)
    settings.ensure_dirs()
    setup_logging("INFO", settings.log_dir)

    page = PageFetcher(settings).get(sys.argv[1], allow_cache=False)
    payload = extract_embedded_json(page)

    if not payload:
        print("No embedded JSON found - the HTML parser is the right approach here.")
        return 0

    out = Path(settings.cache_dir) / "embedded_payload.json"
    out.write_text(json.dumps(payload, indent=2)[:5_000_000], encoding="utf-8")
    print(f"Embedded JSON saved to {out}\n")

    hits = find_collections(payload, *INTERESTING)
    if not hits:
        print("Found JSON, but nothing that looks like race/runner collections.")
        return 0

    print("Candidate collections:")
    for path, value in hits[:40]:
        size = len(value) if isinstance(value, list) else len(value.keys())
        preview = ""
        if isinstance(value, list) and value and isinstance(value[0], dict):
            preview = "  keys: " + ", ".join(list(value[0])[:10])
        print(f"  {path:<60} ({size} items){preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
