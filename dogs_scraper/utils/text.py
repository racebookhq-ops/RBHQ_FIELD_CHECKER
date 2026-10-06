"""Small, dependency-free cleaners for scraped strings."""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_MONEY = re.compile(r"[^0-9.]")


def clean(value: str | None) -> str | None:
    """Collapse whitespace, normalise unicode, return None if nothing is left."""
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace(" ", " ")
    text = _WS.sub(" ", text).strip()
    return text or None


def first(*values: str | None) -> str | None:
    """Return the first value that survives cleaning. Handy for selector fallbacks."""
    for v in values:
        c = clean(v)
        if c:
            return c
    return None


def to_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    m = re.search(r"-?\d+", str(value))
    return int(m.group()) if m else None


def to_float(value: str | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(m.group()) if m else None


def distance_m(value: str | None) -> int | None:
    """'520m' / '520 metres' -> 520"""
    if not value:
        return None
    m = re.search(r"(\d{3,4})\s*m", str(value), re.I)
    if m:
        return int(m.group(1))
    return to_int(value)


def money(value: str | None) -> str | None:
    """Keep prize money as printed, not parsed into cents."""
    return clean(value)


def slugify(value: str | None) -> str | None:
    if not value:
        return None
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or None


def normalise_dog_name(value: str | None) -> str | None:
    """Upper-case, punctuation-stripped name for matching against our own fields.

    Kept separate from the printed name so the raw value is still auditable.
    """
    c = clean(value)
    if not c:
        return None
    return re.sub(r"[^A-Z0-9 ]", "", c.upper()).strip()
