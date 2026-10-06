"""Runtime settings. Defaults live here; config.yaml overrides them."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

BASE_URL = "https://www.thedogs.com.au"


@dataclass
class Settings:
    # --- source -------------------------------------------------------------
    base_url: str = BASE_URL
    # "auto"      -> use embedded JSON when the page exposes it, else HTML
    # "json"      -> embedded JSON only (fail loudly if absent)
    # "html"      -> HTML selectors only
    extraction_mode: str = "auto"
    # "fetcher"   -> plain HTTP with TLS impersonation (fast, default)
    # "stealthy"  -> real browser with anti-bot bypass (slow, use if blocked)
    # "dynamic"   -> plain Playwright browser
    fetcher: str = "fetcher"
    impersonate: str = "chrome"

    # --- politeness ---------------------------------------------------------
    request_timeout: int = 30
    retries: int = 3
    retry_delay: float = 1.0
    delay_between_requests: float = 1.0     # seconds; be a good citizen
    max_concurrency: int = 4                # used by the async path only
    user_agent: str | None = None           # None -> Scrapling picks a real one

    # --- scope --------------------------------------------------------------
    states: list[str] = field(default_factory=list)   # empty = all states
    tracks: list[str] = field(default_factory=list)   # empty = all tracks (slug match)
    include_trials: bool = False

    # --- output -------------------------------------------------------------
    output_dir: Path = PROJECT_ROOT / "output"
    cache_dir: Path = PROJECT_ROOT / ".cache"
    log_dir: Path = PROJECT_ROOT / "logs"
    use_cache: bool = True                  # reuse fetched HTML within cache_ttl
    cache_ttl_minutes: int = 10
    # Housekeeping. Days of results to keep and hours of cached pages to keep;
    # a negative value disables that sweep. 0 output days keeps today only.
    output_retention_days: int = 14
    cache_retention_hours: int = 24
    write_json: bool = True
    write_csv: bool = True
    pretty_json: bool = True

    # --- diagnostics --------------------------------------------------------
    log_level: str = "INFO"
    save_raw_html: bool = False             # dump each page to .cache/raw for selector work

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides: Any) -> "Settings":
        """Build settings from config.yaml (if present) plus keyword overrides."""
        data: dict[str, Any] = {}
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        if path.exists():
            try:
                import yaml  # optional dependency
                loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if isinstance(loaded, dict):
                    data.update(loaded)
            except ImportError:
                pass

        data.update({k: v for k, v in overrides.items() if v is not None})

        valid = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in valid}
        for key in ("output_dir", "cache_dir", "log_dir"):
            if key in clean and clean[key] is not None:
                clean[key] = Path(clean[key])
        return cls(**clean)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in d.items()}

    def ensure_dirs(self) -> None:
        for p in (self.output_dir, self.cache_dir, self.log_dir):
            Path(p).mkdir(parents=True, exist_ok=True)
