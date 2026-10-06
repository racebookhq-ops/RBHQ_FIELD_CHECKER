"""Allow `python -m rbhq_scraper`."""

import sys

from .cli import main

sys.exit(main())
