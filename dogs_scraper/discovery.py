"""Find a structured JSON payload inside a page before falling back to HTML.

Most modern racing sites ship the whole card as JSON in the page (Next.js
`__NEXT_DATA__`, Nuxt `__NUXT__`, or a plain `application/json` script tag).
Parsing that is far more stable than chasing CSS classes, so we always look
for it first.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

from .utils.logging import get_logger

log = get_logger("discovery")

_ASSIGNMENT_PATTERNS = (
    re.compile(r"window\.__NUXT__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S),
    re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S),
    re.compile(r"window\.__DATA__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S),
)

# Endpoint shapes worth trying if the page itself carries nothing useful.
API_CANDIDATES = (
    "/api/v1/racing/{date}",
    "/api/racing/{date}",
    "/racing/{date}.json",
)


def extract_embedded_json(page) -> dict[str, Any] | None:
    """Return the first parsable JSON blob embedded in the page, or None."""
    html = getattr(page, "html_content", None) or getattr(page, "text", "") or ""
    if not html:
        return None

    # 1. Framework hydration payloads with a known id.
    for selector in ('script#__NEXT_DATA__::text', 'script[type="application/json"]::text'):
        try:
            for blob in page.css(selector):
                data = _safe_json(str(blob))
                if isinstance(data, dict) and data:
                    log.debug("found embedded JSON via %s", selector)
                    return data
        except Exception:  # selector unsupported on this object
            continue

    # 2. Bare `window.X = {...}` assignments.
    for pattern in _ASSIGNMENT_PATTERNS:
        m = pattern.search(html)
        if m:
            data = _safe_json(m.group(1))
            if isinstance(data, dict) and data:
                log.debug("found embedded JSON via window assignment")
                return data

    return None


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def walk(node: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    """Depth-first walk of a nested JSON structure, yielding (path, value)."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk(value, f"{path}[{i}]")


def find_collections(data: dict[str, Any], *keys: str) -> list[tuple[str, Any]]:
    """Locate lists/dicts anywhere in the payload whose key matches any of `keys`.

    Used by `tools/inspect_json.py` to work out where the runners actually live
    without hand-tracing the payload.
    """
    wanted = {k.lower() for k in keys}
    hits: list[tuple[str, Any]] = []
    for path, value in walk(data):
        leaf = path.rsplit(".", 1)[-1].split("[")[0].lower()
        if leaf in wanted and isinstance(value, (list, dict)) and value:
            hits.append((path, value))
    return hits
