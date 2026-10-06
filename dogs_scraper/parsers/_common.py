"""Selector helpers shared by the meeting and race parsers."""

from __future__ import annotations

from typing import Any, Iterable

from ..utils.text import clean


def try_selectors(node, candidates: Iterable[str]) -> str | None:
    """Return the first non-empty result from a list of candidate selectors."""
    for selector in candidates:
        try:
            value = node.css(selector).extract_first()
        except Exception:
            continue
        if value is None:
            continue
        text = clean(str(value))
        if text:
            return text
    return None


def try_selectors_all(node, candidates: Iterable[str]) -> list[Any]:
    """Return the first candidate selector that matches anything, as a list."""
    for selector in candidates:
        try:
            found = node.css(selector)
        except Exception:
            continue
        if found:
            return list(found)
    return []


def has_any(node, candidates: Iterable[str]) -> bool:
    for selector in candidates:
        try:
            if len(node.css(selector)) > 0:
                return True
        except Exception:
            continue
    return False


def node_text(node) -> str | None:
    """All text inside a node, descendants included.

    `.text` is only the element's own text node, so it comes back empty for a
    cell whose content is wrapped in a link or a span - which on this site is
    most of them. `get_all_text` walks the subtree; the getattr fallback keeps
    this working against a plain object in tests.
    """
    if node is None:
        return None
    getter = getattr(node, "get_all_text", None)
    if callable(getter):
        try:
            return clean(getter())
        except Exception:
            pass
    return clean(getattr(node, "text", None))


def absolute(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith("http"):
        return href
    if not href.startswith("/"):
        href = "/" + href
    return base_url.rstrip("/") + href
