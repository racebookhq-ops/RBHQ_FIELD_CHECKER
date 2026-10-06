"""Runtime settings. Defaults live here; the `harness:` block of config.yaml
overrides them, and CLI flags override that.

`HARNESS_USER_AGENT` may be set in the environment or the gitignored `.env`
(same loader as rbhq_scraper). Nothing here is a secret - the site needs no key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

#: The key in config.yaml holding this block.
CONFIG_SECTION = "harness"

BASE_URL = "https://www.harness.org.au"
API_HOST = "api.harness.org.au"

#: A browser UA with a clear suffix saying who we are. If Cloudflare ever
#: rejects it, set `user_agent: null` in config.yaml to use the browser default.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 "
    "RacebookHQ-FieldsCheck/1.0"
)


@dataclass
class Settings:
    # --- source -------------------------------------------------------------
    base_url: str = BASE_URL
    # "stealthy" -> Scrapling StealthyFetcher (gets past Cloudflare)
    # "dynamic"  -> plain Playwright via DynamicFetcher
    fetcher: str = "stealthy"
    headless: bool = True                   # --headful flips this for debugging
    solve_cloudflare: bool = True
    user_agent: str | None = DEFAULT_USER_AGENT

    # --- politeness ---------------------------------------------------------
    request_timeout: int = 60               # seconds, per page
    retries: int = 3
    retry_delay: float = 2.0                # backoff: delay * attempt
    delay_min: float = 1.0                  # random pause between pages
    delay_max: float = 3.0
    max_concurrency: int = 1                # one browser context, pages one at a time; capped at 2

    # --- scope --------------------------------------------------------------
    states: list[str] = field(default_factory=list)   # empty = all states
    include_trials: bool = False

    # --- output -------------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / "data"
    log_dir: Path = PROJECT_ROOT / "logs"
    write_json: bool = True
    write_csv: bool = True
    pretty_json: bool = True

    # --- diagnostics --------------------------------------------------------
    log_level: str = "INFO"

    @property
    def output_root(self) -> Path:
        return Path(self.data_dir) / "harness"

    @property
    def raw_root(self) -> Path:
        return Path(self.data_dir) / "raw"

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides: Any) -> "Settings":
        """Build settings from the `harness:` block of config.yaml plus overrides."""
        from rbhq_scraper.env import load_env
        load_env()

        data: dict[str, Any] = {}
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        if path.exists():
            try:
                import yaml  # optional dependency
                loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                block = loaded.get(CONFIG_SECTION) if isinstance(loaded, dict) else None
                if isinstance(block, dict):
                    data.update(block)
            except ImportError:
                pass

        env_ua = os.environ.get("HARNESS_USER_AGENT")
        if env_ua:
            data["user_agent"] = env_ua

        data.update({k: v for k, v in overrides.items() if v is not None})

        valid = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in valid}
        for key in ("data_dir", "log_dir"):
            if key in clean and clean[key] is not None:
                clean[key] = Path(clean[key])
        s = cls(**clean)
        s.max_concurrency = max(1, min(2, int(s.max_concurrency)))
        s.states = [x.strip().upper() for x in (s.states or []) if x and x.strip()]
        return s

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in d.items()}

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.log_dir):
            Path(p).mkdir(parents=True, exist_ok=True)
