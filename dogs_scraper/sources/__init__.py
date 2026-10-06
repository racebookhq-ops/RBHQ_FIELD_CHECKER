"""Data sources. Every source returns the same DayCard shape.

    thedogs.com.au (scraped) - the published fields

Adding another source means writing one class with a `fetch_day` method.
"""

from .base import Source
from .thedogs import TheDogsSource

__all__ = ["Source", "TheDogsSource", "get_source"]


def get_source(name: str, settings=None):
    """Look up a source by name: 'thedogs'."""
    from ..config import Settings
    settings = settings or Settings.load()
    sources = {
        "thedogs": TheDogsSource,
    }
    if name not in sources:
        raise ValueError(f"unknown source '{name}' - choose from {sorted(sources)}")
    return sources[name](settings)
