"""One real browser, pages loaded one at a time, API responses captured.

The race pages are a JavaScript app behind Cloudflare. We never call
api.harness.org.au ourselves - the page makes its own requests, and a
Playwright `response` listener (registered through Scrapling's `page_setup`
hook, i.e. before navigation) keeps the ones we care about. The bodies are
read in `page_action`, while the page is still open.

Everything that touches the network goes through HarnessBrowser, so retries,
backoff and the polite delay between pages live in exactly one place.
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .config import API_HOST, Settings
from .logging import get_logger

log = get_logger("browser")

#: Only responses from the site's own API, and only the racing endpoints.
_API_RE = re.compile(rf"^https://{re.escape(API_HOST)}/racing[/?]")


class FetchError(RuntimeError):
    """Raised when a page could not be retrieved after all retries."""


@dataclass
class Capture:
    """What one page load produced."""

    url: str
    status: int | None = None
    html: str = ""
    #: API URL -> parsed JSON body, for 200 responses that held JSON
    json: dict[str, Any] = field(default_factory=dict)

    def find(self, pattern: str | re.Pattern) -> Any | None:
        """The parsed JSON of the first captured API response whose URL matches."""
        rx = re.compile(pattern) if isinstance(pattern, str) else pattern
        for url, body in self.json.items():
            if rx.search(url):
                return body
        return None


class _ResponseTap:
    """Collects matching responses during a page load."""

    def __init__(self, expect: re.Pattern | None, wait_seconds: float = 20.0):
        self.expect = expect
        self.wait_seconds = wait_seconds
        self._responses: list[Any] = []
        self.bodies: dict[str, Any] = {}

    # -- page_setup(page): runs before navigation ----------------------------
    def setup(self, page) -> None:
        page.on("response", self._on_response)

    def _on_response(self, response) -> None:
        try:
            if _API_RE.match(response.url) and response.request.resource_type in ("xhr", "fetch"):
                self._responses.append(response)
        except Exception:                                  # noqa: BLE001 - never break the page
            pass

    # -- page_action(page): runs once the page has loaded --------------------
    def action(self, page):
        deadline = time.monotonic() + self.wait_seconds
        while self.expect is not None and time.monotonic() < deadline:
            if any(self.expect.search(r.url) for r in self._responses):
                break
            page.wait_for_timeout(300)
        for resp in self._responses:
            if resp.status != 200:
                continue
            try:
                self.bodies[resp.url] = json.loads(resp.body())
            except Exception as exc:                       # noqa: BLE001
                log.debug("could not read %s: %s", resp.url, exc)
        return page


class HarnessBrowser:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._session = None
        self._last_page_at: float | None = None

    # -- lifecycle ------------------------------------------------------------
    def __enter__(self) -> "HarnessBrowser":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> None:
        if self._session is not None:
            return
        try:
            from scrapling.fetchers import DynamicSession, StealthySession
        except ImportError as exc:  # pragma: no cover
            raise FetchError("Scrapling is not installed. Run:  pip install -r requirements.txt") from exc

        s = self.settings
        kwargs: dict[str, Any] = dict(
            headless=s.headless,
            network_idle=True,
            timeout=s.request_timeout * 1000,
        )
        if s.user_agent:
            kwargs["useragent"] = s.user_agent
        if (s.fetcher or "stealthy").lower() == "dynamic":
            self._session = DynamicSession(**kwargs)
        else:
            self._session = StealthySession(solve_cloudflare=s.solve_cloudflare, **kwargs)
        self._session.start()
        log.debug("browser session started (%s, headless=%s)", type(self._session).__name__, s.headless)

    def close(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            finally:
                self._session = None

    # -- politeness -----------------------------------------------------------
    def _pause(self) -> None:
        if self._last_page_at is None:
            return
        gap = random.uniform(self.settings.delay_min, self.settings.delay_max)
        wait = gap - (time.monotonic() - self._last_page_at)
        if wait > 0:
            time.sleep(wait)

    # -- public API -----------------------------------------------------------
    def fetch(self, url: str, expect: str | re.Pattern | None = None) -> Capture:
        """Load `url`; return its HTML plus every captured API JSON body.

        `expect` is a regex for the API URL this page is meant to trigger. If it
        does not turn up, the load is retried; after the last attempt the
        Capture is returned anyway (without that JSON) so the caller can fall
        back to the rendered text.
        """
        self.open()
        rx = re.compile(expect) if isinstance(expect, str) else expect
        last_error: Exception | None = None
        best: Capture | None = None

        for attempt in range(1, self.settings.retries + 1):
            self._pause()
            tap = _ResponseTap(rx)
            try:
                log.info("GET %s%s", url, "" if attempt == 1 else f"  (attempt {attempt})")
                page = self._session.fetch(url, page_setup=tap.setup, page_action=tap.action)
                self._last_page_at = time.monotonic()
                status = getattr(page, "status", None)
                if status and status >= 400:
                    raise FetchError(f"HTTP {status} for {url}")
                cap = Capture(url=url, status=status,
                              html=getattr(page, "html_content", "") or "", json=tap.bodies)
                best = cap
                if rx is None or cap.find(rx) is not None:
                    return cap
                log.warning("expected API response /%s/ not captured (%s/%s)",
                            rx.pattern, attempt, self.settings.retries)
            except Exception as exc:                       # noqa: BLE001 - retry on anything network-ish
                self._last_page_at = time.monotonic()
                last_error = exc
                log.warning("fetch failed (%s/%s): %s", attempt, self.settings.retries, exc)
            if attempt < self.settings.retries:
                time.sleep(self.settings.retry_delay * attempt)

        if best is not None:
            return best
        raise FetchError(f"Could not fetch {url}: {last_error}")
