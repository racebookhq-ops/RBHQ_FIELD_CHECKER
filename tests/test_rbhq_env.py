"""Tests for reading the API key out of `.env`.

The rule that matters: a real exported variable always beats the file, so a
scheduled run or CI can supply the key its own way without anyone editing a
checked-out `.env`.
"""

import os

import pytest

from rbhq_scraper import env as env_module
from rbhq_scraper.config import FeedConfig
from rbhq_scraper.env import load_env, reset_for_tests, source_of

KEY = "TEST_DOTENV_KEY"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    """Each test starts with no cached load and no stray variable."""
    monkeypatch.delenv(KEY, raising=False)
    reset_for_tests()
    yield
    monkeypatch.delenv(KEY, raising=False)
    reset_for_tests()


def write_env(tmp_path, body):
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    return path


# -- loading ---------------------------------------------------------------
def test_value_is_read_from_the_file(tmp_path):
    load_env(write_env(tmp_path, f"{KEY}=from-the-file\n"))
    assert os.environ[KEY] == "from-the-file"
    assert source_of(KEY) == ".env"


def test_an_exported_variable_wins(tmp_path, monkeypatch):
    """CI and scheduled runs must not be overridden by a checked-out file."""
    monkeypatch.setenv(KEY, "from-the-environment")
    load_env(write_env(tmp_path, f"{KEY}=from-the-file\n"))

    assert os.environ[KEY] == "from-the-environment"
    assert source_of(KEY) == "environment"


def test_quotes_comments_and_export_are_handled(tmp_path):
    load_env(write_env(tmp_path, "\n".join([
        "# a comment",
        "",
        f'export {KEY}="quoted value"',
    ])))
    assert os.environ[KEY] == "quoted value"


def test_a_blank_value_counts_as_unset(tmp_path):
    """`.env.example` ships with an empty key - that must not look configured."""
    load_env(write_env(tmp_path, f"{KEY}=\n"))
    cfg = FeedConfig(api_key_env=KEY)
    assert cfg.api_key is None


def test_missing_file_is_not_an_error(tmp_path):
    assert load_env(tmp_path / "nope.env") is None
    assert source_of(KEY) == "not set"


def test_loading_happens_once(tmp_path):
    path = write_env(tmp_path, f"{KEY}=first\n")
    load_env(path)
    assert os.environ[KEY] == "first"

    # A second call is a no-op, even though the file changed.
    path.write_text(f"{KEY}=second\n", encoding="utf-8")
    load_env(path)
    assert os.environ[KEY] == "first"

    # ...unless it is forced.
    del os.environ[KEY]
    load_env(path, force=True)
    assert os.environ[KEY] == "second"


# -- how the config uses it ------------------------------------------------
def test_config_picks_the_key_up_without_being_told(tmp_path, monkeypatch):
    monkeypatch.setattr(env_module, "DEFAULT_ENV_PATH",
                        write_env(tmp_path, f"{KEY}=sekrit\n"))
    cfg = FeedConfig(api_key_env=KEY)

    assert cfg.api_key == "sekrit"
    assert cfg.headers_for()["Authorization"] == "Bearer sekrit"


def test_describe_names_the_source_but_never_the_key(tmp_path, monkeypatch):
    monkeypatch.setattr(env_module, "DEFAULT_ENV_PATH",
                        write_env(tmp_path, f"{KEY}=sekrit\n"))
    described = FeedConfig(api_key_env=KEY).describe()

    assert "sekrit" not in described
    assert ".env" in described and KEY in described


def test_unset_key_tells_you_where_to_put_it(tmp_path, monkeypatch):
    monkeypatch.setattr(env_module, "DEFAULT_ENV_PATH", tmp_path / "absent.env")
    described = FeedConfig(api_key_env=KEY).describe()
    assert "is not set" in described and ".env" in described


# -- the shipped template --------------------------------------------------
def test_example_file_is_present_and_blank():
    from pathlib import Path
    example = Path(__file__).resolve().parent.parent / ".env.example"
    assert example.exists(), ".env.example should be committed as the template"

    text = example.read_text(encoding="utf-8")
    assert "RBHQ_API_KEY=" in text
    # It must not carry a value - it is committed.
    for line in text.splitlines():
        if line.startswith("RBHQ_API_KEY="):
            assert line.strip() == "RBHQ_API_KEY="


def test_dotenv_is_not_committed():
    """A real .env must stay out of the repo - it is gitignored for a reason."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    assert ".env" in (root / ".gitignore").read_text(encoding="utf-8").split()
