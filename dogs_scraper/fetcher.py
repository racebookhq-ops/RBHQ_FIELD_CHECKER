"""Thin wrapper over Scrapling's fetchers.

Everything that touches the network goes through PageFetcher so retries,
throttling, caching and raw-HTML dumping are handled in exactly one place.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path

from .config import Settings
from .utils.logging import get_logger

log = get_logger("fetcher")


class FetchError(RuntimeError):
    """Raised when a page could not be retrieved after all retries."""


class PageFetcher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._last_request_at: float = 0.0
        self._backend = None
        self._session = None

    # -- backend selection ---------------------------------------------------
    def _load_backend(self):
        if self._backend is not None:
            return self._backend
        try:
            from scrapling.fetchers import Fetcher, StealthyFetcher, DynamicFetcher
        except ImportError as exc:  # pragma: no cover
            raise FetchError(
                "Scrapling is not installed. Run:  pip install -r requirements.txt"
            ) from exc

        mode = (self.settings.fetcher or "fetcher").lower()
        self._backend = {
            "fetcher": Fetcher,
            "stealthy": StealthyFetcher,
            "dynamic": DynamicFetcher,
        }.get(mode, Fetcher)
        log.debug("Using %s backend", self._backend.__name__)
        return self._backend

    # -- caching -------------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        return Path(self.settings.cache_dir) / f"{digest}.html"

    def _read_cache(self, url: str) -> str | None:
        if not self.settings.use_cache:
            return None
        path = self._cache_path(url)
        if not path.exists():
            return None
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        if age > timedelta(minutes=self.settings.cache_ttl_minutes):
            return None
        log.debug("cache hit  %s", url)
        return path.read_text(encoding="utf-8", errors="replace")

    def _write_cache(self, url: str, html: str) -> None:
        if not self.settings.use_cache:
            return
        path = self._cache_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8", errors="replace")

    def _dump_raw(self, url: str, html: str) -> None:
        if not self.settings.save_raw_html:
            return
        raw_dir = Path(self.settings.cache_dir) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        name = url.replace("https://", "").replace("/", "_")[:120] + ".html"
        (raw_dir / name).write_text(html, encoding="utf-8", errors="replace")

    # -- throttling ----------------------------------------------------------
    def _throttle(self) -> None:
        gap = self.settings.delay_between_requests
        if gap <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_request_at = time.monotonic()

    # -- public API ----------------------------------------------------------
    def get(self, url: str, *, allow_cache: bool = True):
        """Fetch a URL and return a Scrapling Selector/Response.

        Cached HTML is re-parsed into a Selector so callers get one type back.
        """
        if allow_cache:
            cached = self._read_cache(url)
            if cached is not None:
                return self._to_selector(cached, url)

        backend = self._load_backend()
        last_error: Exception | None = None

        for attempt in range(1, self.settings.retries + 1):
            self._throttle()
            try:
                log.info("GET %s%s", url, "" if attempt == 1 else f"  (attempt {attempt})")
                if backend.__name__ == "Fetcher":
                    page = backend.get(
                        url,
                        timeout=self.settings.request_timeout,
                        stealthy_headers=True,
                        impersonate=self.settings.impersonate,
                        retries=1,
                    )
                else:
                    page = backend.fetch(url, timeout=self.settings.request_timeout * 1000)

                status = getattr(page, "status", 200)
                if status and status >= 400:
                    raise FetchError(f"HTTP {status} for {url}")

                html = getattr(page, "html_content", None) or getattr(page, "text", "") or ""
                if html:
                    self._write_cache(url, html)
                    self._dump_raw(url, html)
                return page

            except Exception as exc:  # noqa: BLE001 - we retry on anything network-ish
                last_error = exc
                log.warning("fetch failed (%s/%s): %s", attempt, self.settings.retries, exc)
                if attempt < self.settings.retries:
                    time.sleep(self.settings.retry_delay * attempt)

        raise FetchError(f"Could not fetch {url}: {last_error}")

    @staticmethod
    def _to_selector(html: str, url: str):
        from scrapling import Selector
        return Selector(content=html, url=url)
