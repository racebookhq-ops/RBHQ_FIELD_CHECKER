#!/usr/bin/env python
"""Print the shape of a captured harness API response.

    python tools/inspect_harness_json.py tests/fixtures/harness/meeting_api.json
    python tools/inspect_harness_json.py data/raw/2026-10-06/APC06102601.json --items 2

Keys, types and a short example value for each, with lists shown by their first
item(s). Use it to check mapper.py against a fresh capture when the API changes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def shape(obj, depth: int = 0, key: str = "", items: int = 1) -> None:
    pad = "  " * depth
    if isinstance(obj, dict):
        print(f"{pad}{key}{{}}  ({len(obj)} keys)")
        for k, v in obj.items():
            shape(v, depth + 1, f"{k}: ", items)
    elif isinstance(obj, list):
        print(f"{pad}{key}[]  (n={len(obj)})")
        for x in obj[:items]:
            shape(x, depth + 1, "- ", items)
    else:
        print(f"{pad}{key}{type(obj).__name__} = {json.dumps(obj, ensure_ascii=False)[:80]}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", type=Path)
    p.add_argument("--items", type=int, default=1, help="list items to expand (default 1)")
    args = p.parse_args()
    if not args.file.exists():
        print(f"{args.file} not found - run tools/dump_harness.py first.")
        return 1
    shape(json.loads(args.file.read_text(encoding="utf-8")), items=args.items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
