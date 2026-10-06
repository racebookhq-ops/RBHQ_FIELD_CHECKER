"""Getting the feed payload.

`fetch_day` is the normal path: one POST per racing day, with the endpoint and
body described by `config.yaml` (see config.py). `load_file` replays a saved
response instead, which keeps the tests offline and makes debugging a report
free.

Nothing here is cached. The point of the comparison is to catch a scratching or
a box change soon after it happens, so serving a card from a cache would
quietly defeat it.
"""

from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path
from typing import Any

from .config import FeedConfig
from .logging import get_logger

log = get_logger("client")


class FeedError(RuntimeError):
    """The payload could not be fetched, or does not look like the feed."""


class FeedNotConfigured(FeedError):
    """No endpoint has been set, so there is nothing to call."""


def fetch_day(day: _date, config: FeedConfig | None = None) -> dict[str, Any]:
    """Fetch one racing day from the feed."""
    config = config or FeedConfig.load()
    if not config.configured:
        raise FeedNotConfigured(
            "No feed endpoint configured. Set `rbhq.base_url` (and `path`) in "
            "config.yaml, or pass --url. To work from a saved response instead, "
            "pass --file."
        )

    try:
        from scrapling.fetchers import Fetcher
    except ImportError as exc:                              # pragma: no cover
        raise FeedError("Scrapling is not installed. Run: "
                        "pip install -r requirements.txt") from exc

    url = config.url_for(day)
    params = config.query_for(day)
    headers = config.headers_for()
    body = config.body_for(day)

    method = str(config.method or "POST").upper()
    send = getattr(Fetcher, method.lower(), None)
    if send is None:
        raise FeedError(f"unsupported method {method!r} - use GET or POST")

    # The body is safe to log; the key is never in it, whichever way it is sent.
    log.info("%s %s %s", method, url, body if method != "GET" else params)

    call: dict[str, Any] = dict(
        params=params or None,
        headers=headers,
        timeout=config.timeout,
        retries=config.retries,
        retry_delay=config.retry_delay,
        impersonate=config.impersonate,
        verify=config.verify,
    )
    if method != "GET":
        call["json"] = body

    try:
        response = send(url, **call)
    except Exception as exc:                # noqa: BLE001 - surfaced, not raised raw
        raise FeedError(f"could not reach {url}: {exc}") from exc

    status = getattr(response, "status", 200)
    if status and status >= 400:
        raise FeedError(_status_hint(status, url, config))

    try:
        payload = response.json()
    except Exception as exc:                # noqa: BLE001 - any parser failure
        head = str(getattr(response, "body", "") or "")[:200]
        raise FeedError(f"{url} did not return JSON ({exc}). First bytes: {head!r}") from exc

    return _validate(payload, url)


def _status_hint(status: int, url: str, config: FeedConfig) -> str:
    """Turn an HTTP status into something worth reading at 6am."""
    if status in (401, 403):
        if not config.api_key:
            return (f"feed returned HTTP {status} for {url} - no API key was sent. "
                    f"Put {config.api_key_env}=... in .env (copy .env.example), "
                    f"or export it.")
        return (f"feed returned HTTP {status} for {url} - the key was rejected. "
                f"{config.api_key_env} came from {config.api_key_source}; it is "
                f"sent as {config.auth_header or config.auth_param}. Check the "
                f"value, and that `rbhq.auth_prefix` matches what the API wants.")
    if status == 404:
        return f"feed returned HTTP 404 for {url} - check `rbhq.path`."
    if status in (400, 422):
        return (f"feed returned HTTP {status} for {url} - the request body was "
                f"rejected. Check `rbhq.date_format` and `rbhq.race_types`; run "
                f"--show-endpoint to see exactly what is being sent.")
    if status == 405:
        return (f"feed returned HTTP 405 for {url} - wrong method. "
                f"`rbhq.method` is currently {config.method}.")
    if status == 429:
        return f"feed returned HTTP 429 for {url} - rate limited; retry later."
    return f"feed returned HTTP {status} for {url}"


def load_file(path: str | Path) -> dict[str, Any]:
    """Replay a saved feed response."""
    path = Path(path)
    if not path.exists():
        raise FeedError(f"no such file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FeedError(f"{path} is not valid JSON: {exc}") from exc
    log.info("read %s", path)
    return _validate(payload, str(path))


def save_response(payload: dict[str, Any], path: str | Path) -> Path:
    """Write a fetched payload out, so a run can be replayed later."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("saved raw response to %s", path)
    return path


def _validate(payload: Any, origin: str) -> dict[str, Any]:
    """Fail on the wrong shape here, rather than silently mapping nothing."""
    if not isinstance(payload, dict):
        raise FeedError(f"{origin}: expected a JSON object, got {type(payload).__name__}")
    if "meetings" not in payload:
        keys = ", ".join(sorted(str(k) for k in payload)[:8]) or "(none)"
        raise FeedError(f"{origin}: no 'meetings' key - is this the right endpoint? "
                        f"Top-level keys were: {keys}")
    if not isinstance(payload["meetings"], list):
        raise FeedError(f"{origin}: 'meetings' is not a list")
    return payload
