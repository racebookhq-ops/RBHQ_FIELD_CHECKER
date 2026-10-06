"""harness.org.au as a Source.

Implements the same `Source` contract as dogs_scraper.sources (`fetch_day`), so
the comparison layer can drive it the same way later. Nothing is compared or
alerted from here - that is out of scope for now.
"""

from __future__ import annotations

from datetime import date as _date

from dogs_scraper.sources.base import Source

from .models import DayCard
from .scraper import HarnessScraper


class HarnessSource(Source):
    name = "harness"

    def fetch_day(self, day: _date) -> DayCard:
        return HarnessScraper(self.settings).scrape_day(day)
