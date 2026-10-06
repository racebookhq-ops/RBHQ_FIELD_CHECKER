"""Where the feed lives and how to call it.

    POST https://api.racebookhq.com/api/host/events/full
    {
      "dates": ["2026-09-22T00:00:00"],
      "raceTypes": ["G"]
    }

`raceTypes` selects the codes: **G** greyhounds, **R** thoroughbreds,
**H** harness. Only G is requested by default - the other two have nothing on
thedogs.com.au to be compared against, and asking for them makes the response
several times larger for no gain.

Everything here can be overridden from the `rbhq:` block in `config.yaml`, so a
changed path or an added parameter does not need a code change. Credentials are
the exception: `api_key_env` names an environment variable, read at call time.
The value can live in a gitignored `.env` in the project root - see env.py -
but it never goes in `config.yaml`, which is meant to be committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Any

from .env import load_env, source_of

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

#: The key in config.yaml holding this block.
CONFIG_SECTION = "rbhq"

#: Greyhounds. The feed also serves "R" (thoroughbred) and "H" (harness).
GREYHOUND_CODE = "G"
HARNESS_CODE = "H"
HARNESS_CODE = "H"
THOROUGHBRED_CODE = "R"


@dataclass
class FeedConfig:
    # --- endpoint -----------------------------------------------------------
    base_url: str = "https://api.racebookhq.com"
    path: str = "/api/host/events/full"
    method: str = "POST"

    # --- request body -------------------------------------------------------
    #: Body key carrying the racing day. The API takes a list of them.
    date_field: str = "dates"
    #: Midnight, no zone suffix - the shape the API documents.
    date_format: str = "%Y-%m-%dT00:00:00"
    date_as_list: bool = True
    race_types_field: str = "raceTypes"
    race_types: list[str] = field(default_factory=lambda: [GREYHOUND_CODE])
    #: Any other fixed body fields.
    body: dict[str, Any] = field(default_factory=dict)

    # --- request extras -----------------------------------------------------
    params: dict[str, Any] = field(default_factory=dict)      # query string
    headers: dict[str, str] = field(default_factory=dict)

    # --- auth ---------------------------------------------------------------
    #: Send the key as a header (usual), or as a query parameter. The endpoint
    #: may not need one at all, in which case leave the variable unset.
    auth_header: str | None = "Authorization"
    auth_prefix: str = "Bearer "
    auth_param: str | None = None
    #: Environment variable holding the key. Never the key itself.
    api_key_env: str = "RBHQ_API_KEY"

    # --- transport ----------------------------------------------------------
    timeout: int = 30
    retries: int = 3
    retry_delay: float = 1.0
    impersonate: str = "chrome"
    verify: bool = True

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides: Any) -> "FeedConfig":
        """Read the `rbhq:` block from config.yaml, then apply overrides."""
        data: dict[str, Any] = {}
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        if path.exists():
            try:
                import yaml
                loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                section = loaded.get(CONFIG_SECTION) if isinstance(loaded, dict) else None
                if isinstance(section, dict):
                    # A null in the file means "use the default", not "unset it".
                    data.update({k: v for k, v in section.items() if v is not None})
            except ImportError:                                # pragma: no cover
                pass

        data.update({k: v for k, v in overrides.items() if v is not None})
        valid = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in valid})

    # -- building the call ---------------------------------------------------
    @property
    def api_key(self) -> str | None:
        # .env is read on first use, and never overrides a real exported value.
        load_env()
        return os.environ.get(self.api_key_env) or None

    @property
    def api_key_source(self) -> str:
        """Where the key came from - `.env`, the environment, or nowhere."""
        return source_of(self.api_key_env)

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def url_for(self, day: _date | None = None) -> str:
        base = str(self.base_url or "").rstrip("/")
        path = self.path or "/"
        if day is not None and "{date}" in path:
            path = path.format(date=day.strftime(self.date_format))
        if not path.startswith("/"):
            path = "/" + path
        return base + path

    def body_for(self, day: _date) -> dict[str, Any]:
        """The JSON body for one racing day."""
        stamp = day.strftime(self.date_format)
        payload: dict[str, Any] = dict(self.body)
        if self.date_field:
            payload[self.date_field] = [stamp] if self.date_as_list else stamp
        if self.race_types_field and self.race_types:
            payload[self.race_types_field] = list(self.race_types)
        return payload

    def query_for(self, day: _date) -> dict[str, Any]:
        query = dict(self.params)
        key = self.api_key
        if key and self.auth_param:
            query[self.auth_param] = key
        return query

    def headers_for(self) -> dict[str, str]:
        headers = {"Accept": "application/json",
                   "Content-Type": "application/json", **self.headers}
        key = self.api_key
        if key and self.auth_header:
            headers[self.auth_header] = f"{self.auth_prefix}{key}"
        return headers

    def describe(self) -> str:
        """A one-line summary for logs and errors - never includes the key."""
        auth = "none sent"
        where = self.api_key_source
        if self.api_key and self.auth_header:
            auth = f"{self.auth_header} header from ${self.api_key_env} ({where})"
        elif self.api_key and self.auth_param:
            auth = f"{self.auth_param} param from ${self.api_key_env} ({where})"
        elif self.auth_header or self.auth_param:
            auth = (f"${self.api_key_env} is not set - put it in .env or export it")
        return f"{self.method} {self.url_for()}  auth: {auth}"
