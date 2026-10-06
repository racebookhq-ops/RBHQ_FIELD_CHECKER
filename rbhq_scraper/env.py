"""Loading secrets from a `.env` file.

`.env` sits in the project root, is gitignored, and holds the API key:

    RBHQ_API_KEY=...

Two rules make this safe to rely on:

* **A real environment variable always wins.** Anything already exported - by
  `setx`, a CI secret store, a container - is left alone. The file is a
  convenience for local work, not an override.
* **Loading happens once, lazily**, the first time a key is actually read, so
  importing this package has no side effects.

`python-dotenv` does the parsing, which handles quoting, `export ` prefixes and
comments properly.
"""

from __future__ import annotations

import os
from pathlib import Path

from .logging import get_logger

log = get_logger("env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

#: Where the values came from, for `--show-endpoint`. None until a load is tried.
_loaded_from: Path | None = None
_loaded = False
#: Names this process actually took from the file, as opposed to inheriting.
_from_file: set[str] = set()


def load_env(path: str | Path | None = None, *, force: bool = False) -> Path | None:
    """Read `.env` into the environment, without overriding what is already set.

    Returns the file that was loaded, or None when there was none to load.
    """
    global _loaded, _loaded_from, _from_file
    if _loaded and not force:
        return _loaded_from

    _loaded = True
    _loaded_from, _from_file = None, set()

    env_path = Path(path) if path else DEFAULT_ENV_PATH
    if not env_path.exists():
        return None

    try:
        from dotenv import dotenv_values, load_dotenv
    except ImportError:                                    # pragma: no cover
        log.warning("%s exists but python-dotenv is not installed - run "
                    "pip install -r requirements.txt", env_path.name)
        return None

    # Note what was already exported before touching anything, so we can tell
    # afterwards which values genuinely came from the file.
    already_set = set(os.environ)
    in_file = {k for k, v in dotenv_values(env_path).items() if v is not None}

    # override=False: an exported variable beats the file.
    load_dotenv(env_path, override=False)

    _loaded_from = env_path
    _from_file = in_file - already_set
    log.debug("loaded %s (%d value(s) taken from it)", env_path, len(_from_file))
    return env_path


def source_of(name: str) -> str:
    """Where a variable's value came from - for diagnostics, never its value."""
    load_env()
    if name not in os.environ:
        return "not set"
    if name in _from_file and _loaded_from is not None:
        return _loaded_from.name
    return "environment"


def reset_for_tests() -> None:
    """Forget that a load happened, so a test can point at another file."""
    global _loaded, _loaded_from, _from_file
    _loaded, _loaded_from, _from_file = False, None, set()
