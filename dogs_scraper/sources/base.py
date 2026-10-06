"""The contract every source implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date as _date

from ..config import Settings
from ..models import DayCard


class Source(ABC):
    """A thing that can produce a day's racing card.

    Implementations must return runners keyed on `box`, with `name` populated.
    Everything else is optional.
    """

    #: short name used in CLI flags and config
    name: str = "source"

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    def fetch_day(self, day: _date) -> DayCard:
        """Return the full card for `day`."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"
