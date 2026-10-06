"""thedogs.com.au as a Source - the reference side of the comparison."""

from __future__ import annotations

from datetime import date as _date

from ..models import DayCard
from ..scraper import DogsScraper
from .base import Source


class TheDogsSource(Source):
    name = "thedogs"

    def fetch_day(self, day: _date) -> DayCard:
        card = DogsScraper(self.settings).scrape_day(day)
        card.source = "thedogs.com.au"
        return card
