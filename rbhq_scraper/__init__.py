"""Read the RBHQ greyhound feed and return the same card the dogs scraper does.

    from rbhq_scraper import scrape

    card = scrape("today")
    for meeting in card.meetings:
        for race in meeting.races:
            print(meeting.track, race.race_number, race.field_size, race.scratchings)

The card is a `dogs_scraper.models.DayCard` - the same class, not a lookalike -
so both sources serialise through one implementation and cannot drift apart.
"""

from __future__ import annotations

from datetime import date as _date

from dogs_scraper.models import DayCard, Meeting, Race, Runner, parse_date

from .client import FeedError, FeedNotConfigured, fetch_day, load_file
from .config import FeedConfig, HARNESS_CODE
from .mapper import DEFAULT_COUNTRIES, build_card

__version__ = "0.1.0"

__all__ = [
    "scrape", "scrape_file", "scrape_harness", "build_card", "FeedConfig",
    "FeedError", "FeedNotConfigured",
    "DayCard", "Meeting", "Race", "Runner",
]


def scrape(day: str | _date = "today", config: FeedConfig | None = None,
           **kwargs) -> DayCard:
    """Fetch one racing day from the feed and map it."""
    parsed = parse_date(day)
    return build_card(fetch_day(parsed, config), parsed, **kwargs)


def scrape_harness(day: str | _date = "today", config: FeedConfig | None = None, **kwargs):
    """Fetch one racing day's harness meetings; returns a `harness_scraper` DayCard.

    Mapping is unverified against a real harness response - see harness_mapper.py.
    """
    from .harness_mapper import build_harness_card

    parsed = parse_date(day)
    config = config or FeedConfig.load(race_types=[HARNESS_CODE])
    return build_harness_card(fetch_day(parsed, config), parsed, **kwargs)


def scrape_file(path: str, day: str | _date | None = None, **kwargs) -> DayCard:
    """Map a saved feed response. `day=None` keeps every day in the payload."""
    return build_card(load_file(path), parse_date(day) if day else None, **kwargs)
