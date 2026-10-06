#!/usr/bin/env python
"""Convenience entry point for the whole thing.

    python run.py                     check today's fields, end to end
    python run.py --date tomorrow
    python run.py --strict

That is the same as `python -m field_compare`, which is what it calls. The two
halves can also be run on their own when you want just one card:

    python -m dogs_scraper --date today     what thedogs.com.au publishes
    python -m rbhq_scraper --date today     what the RBHQ feed shows
"""

import sys

from field_compare.cli import main

if __name__ == "__main__":
    sys.exit(main())
