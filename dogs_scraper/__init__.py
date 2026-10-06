"""Scrape today's greyhound fields and runners from thedogs.com.au.

Typical use from another program (e.g. the field-comparison agent):

    from dogs_scraper import scrape
    card = scrape("today")
    for meeting in card.meetings:
        ...
"""

from __future__ import annotations

from datetime import date as _date

from .config import Settings
from .models import DayCard, Meeting, Race, Runner, parse_date
from .scraper import DogsScraper

__version__ = "0.1.0"

__all__ = [
    "scrape", "DogsScraper", "Settings",
    "DayCard", "Meeting", "Race", "Runner",
]


def scrape(day: str | _date = "today", settings: Settings | None = None) -> DayCard:
    """Scrape one racing day and return the structured card."""
    settings = settings or Settings.load()
    settings.ensure_dirs()
    return DogsScraper(settings).scrape_day(parse_date(day))
