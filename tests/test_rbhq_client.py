"""Tests for building and making the feed call.

    POST https://api.racebookhq.com/api/host/events/full
    { "dates": ["2026-09-22T00:00:00"], "raceTypes": ["G"] }

The network is stubbed throughout - these pin how the request is assembled and
how failures are reported, which is what actually goes wrong in the field.
"""

import json
import sys
import types
from datetime import date

import pytest

import rbhq_scraper.client as client
from rbhq_scraper.client import FeedError, FeedNotConfigured, fetch_day, save_response
from rbhq_scraper.config import FeedConfig

DAY = date(2026, 9, 22)


@pytest.fixture
def config():
    return FeedConfig(api_key_env="TEST_FEED_KEY")


class FakeResponse:
    def __init__(self, payload=None, status=200, body=""):
        self._payload, self.status, self.body = payload, status, body

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


@pytest.fixture
def capture(monkeypatch):
    """Stand in for Scrapling's Fetcher and record how it was called."""
    calls = {}

    def _record(method):
        def send(url, **kwargs):
            calls["method"], calls["url"], calls["kwargs"] = method, url, kwargs
            return calls.get("response") or FakeResponse({"meetings": []})
        return send

    fake = types.SimpleNamespace(post=_record("POST"), get=_record("GET"))
    module = types.ModuleType("scrapling.fetchers")
    module.Fetcher = fake
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", module)
    return calls


# -- the defaults are the real endpoint ------------------------------------
def test_defaults_point_at_the_live_endpoint():
    cfg = FeedConfig()
    assert cfg.method == "POST"
    assert cfg.url_for() == "https://api.racebookhq.com/api/host/events/full"
    assert cfg.configured


def test_body_matches_the_documented_shape(config):
    assert config.body_for(DAY) == {
        "dates": ["2026-09-22T00:00:00"],
        "raceTypes": ["G"],
    }


def test_only_greyhounds_are_requested(config):
    """R and H have nothing on thedogs to compare against."""
    assert config.race_types == ["G"]

    config.race_types = ["R", "G", "H"]
    assert config.body_for(DAY)["raceTypes"] == ["R", "G", "H"]


def test_extra_body_fields_are_kept(config):
    config.body = {"includeScratched": True}
    body = config.body_for(DAY)
    assert body["includeScratched"] is True
    assert body["dates"] == ["2026-09-22T00:00:00"]


def test_date_can_live_in_the_path():
    cfg = FeedConfig(base_url="https://api.example.com/", path="racing/{date}/meetings",
                     date_format="%Y-%m-%d")
    assert cfg.url_for(DAY) == "https://api.example.com/racing/2026-09-22/meetings"


# -- auth ------------------------------------------------------------------
def test_api_key_is_read_from_the_environment(config, monkeypatch):
    monkeypatch.delenv("TEST_FEED_KEY", raising=False)
    assert config.api_key is None
    assert "Authorization" not in config.headers_for()

    monkeypatch.setenv("TEST_FEED_KEY", "sekrit")
    assert config.headers_for()["Authorization"] == "Bearer sekrit"


def test_auth_header_and_prefix_are_configurable(config, monkeypatch):
    monkeypatch.setenv("TEST_FEED_KEY", "sekrit")
    config.auth_header, config.auth_prefix = "X-Api-Key", ""
    headers = config.headers_for()
    assert headers["X-Api-Key"] == "sekrit"
    assert "Authorization" not in headers


def test_api_key_can_go_in_the_query_instead(config, monkeypatch):
    monkeypatch.setenv("TEST_FEED_KEY", "sekrit")
    config.auth_header, config.auth_param = None, "apiKey"
    assert config.query_for(DAY)["apiKey"] == "sekrit"
    assert "Authorization" not in config.headers_for()


def test_describe_never_leaks_the_key(config, monkeypatch):
    monkeypatch.setenv("TEST_FEED_KEY", "sekrit")
    assert "sekrit" not in config.describe()
    assert "TEST_FEED_KEY" in config.describe()


# -- making the call -------------------------------------------------------
def test_fetch_posts_the_body_with_headers_and_timeout(config, capture, monkeypatch):
    monkeypatch.setenv("TEST_FEED_KEY", "sekrit")
    capture["response"] = FakeResponse({"meetings": [], "successful": True})

    payload = fetch_day(DAY, config)

    assert payload["meetings"] == []
    assert capture["method"] == "POST"
    assert capture["url"] == "https://api.racebookhq.com/api/host/events/full"

    kwargs = capture["kwargs"]
    assert kwargs["json"] == {"dates": ["2026-09-22T00:00:00"], "raceTypes": ["G"]}
    assert kwargs["headers"]["Authorization"] == "Bearer sekrit"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert (kwargs["timeout"], kwargs["retries"]) == (30, 3)


def test_get_endpoints_send_no_body(config, capture):
    config.method = "GET"
    capture["response"] = FakeResponse({"meetings": []})
    fetch_day(DAY, config)

    assert capture["method"] == "GET"
    assert "json" not in capture["kwargs"]


def test_unsupported_method_is_rejected(config, capture):
    config.method = "TRACE"
    with pytest.raises(FeedError, match="unsupported method"):
        fetch_day(DAY, config)


def test_unconfigured_endpoint_says_so():
    with pytest.raises(FeedNotConfigured, match="No feed endpoint configured"):
        fetch_day(DAY, FeedConfig(base_url=""))


# -- failures worth reading ------------------------------------------------
def test_401_without_a_key_says_where_to_put_one(config, capture, monkeypatch):
    """The live endpoint returns a bare 401 with no body - say something useful."""
    monkeypatch.delenv("TEST_FEED_KEY", raising=False)
    capture["response"] = FakeResponse(status=401)
    with pytest.raises(FeedError, match=r"401.*no API key was sent.*\.env"):
        fetch_day(DAY, config)


def test_401_with_a_key_says_it_was_rejected(config, capture, monkeypatch):
    """A different problem entirely - the key exists but the API said no."""
    monkeypatch.setenv("TEST_FEED_KEY", "sekrit")
    capture["response"] = FakeResponse(status=401)
    with pytest.raises(FeedError, match=r"401.*key was rejected") as caught:
        fetch_day(DAY, config)
    assert "sekrit" not in str(caught.value), "the key must not appear in errors"


def test_rejected_body_points_at_the_body_settings(config, capture):
    capture["response"] = FakeResponse(status=400)
    with pytest.raises(FeedError, match=r"400.*body was rejected.*date_format"):
        fetch_day(DAY, config)


def test_wrong_method_names_the_setting(config, capture):
    capture["response"] = FakeResponse(status=405)
    with pytest.raises(FeedError, match=r"405.*wrong method.*POST"):
        fetch_day(DAY, config)


def test_404_points_at_the_path(config, capture):
    capture["response"] = FakeResponse(status=404)
    with pytest.raises(FeedError, match=r"404.*rbhq.path"):
        fetch_day(DAY, config)


def test_rate_limit_is_named(config, capture):
    capture["response"] = FakeResponse(status=429)
    with pytest.raises(FeedError, match="rate limited"):
        fetch_day(DAY, config)


def test_non_json_response_shows_what_came_back(config, capture):
    capture["response"] = FakeResponse(payload=None, body="<html>gateway error</html>")
    with pytest.raises(FeedError, match="did not return JSON"):
        fetch_day(DAY, config)


def test_wrong_endpoint_lists_the_keys_it_found(config, capture):
    capture["response"] = FakeResponse({"races": [], "status": "ok"})
    with pytest.raises(FeedError, match=r"no 'meetings' key.*races, status"):
        fetch_day(DAY, config)


def test_transport_failure_is_wrapped(config, monkeypatch):
    def boom(url, **kwargs):
        raise OSError("connection refused")

    module = types.ModuleType("scrapling.fetchers")
    module.Fetcher = types.SimpleNamespace(post=boom, get=boom)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", module)

    with pytest.raises(FeedError, match="could not reach .*connection refused"):
        fetch_day(DAY, config)


# -- replay ----------------------------------------------------------------
def test_saved_response_round_trips(tmp_path, config, capture):
    capture["response"] = FakeResponse({"meetings": [], "successful": True})
    payload = fetch_day(DAY, config)

    path = save_response(payload, tmp_path / "raw.json")
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert client.load_file(path) == payload


# -- config loading --------------------------------------------------------
def test_config_reads_the_rbhq_block(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "base_url: https://www.thedogs.com.au\n"
        "rbhq:\n"
        "  base_url: https://api.example.com\n"
        "  path: /racing/meetings\n"
        "  race_types: [G, R]\n",
        encoding="utf-8")
    cfg = FeedConfig.load(tmp_path / "config.yaml")

    assert cfg.base_url == "https://api.example.com"   # not the scraper's base_url
    assert cfg.path == "/racing/meetings"
    assert cfg.race_types == ["G", "R"]


def test_a_null_in_the_file_keeps_the_default(tmp_path):
    """`auth_param: null` should mean 'leave it alone', not 'blank it'."""
    (tmp_path / "config.yaml").write_text(
        "rbhq:\n  auth_param: null\n  path: /other\n", encoding="utf-8")
    cfg = FeedConfig.load(tmp_path / "config.yaml")
    assert cfg.path == "/other"
    assert cfg.auth_header == "Authorization"          # untouched


def test_overrides_beat_the_file(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "rbhq:\n  base_url: https://api.example.com\n", encoding="utf-8")
    cfg = FeedConfig.load(tmp_path / "config.yaml", base_url="https://other.example")
    assert cfg.base_url == "https://other.example"


def test_missing_config_falls_back_to_the_built_in_endpoint(tmp_path):
    cfg = FeedConfig.load(tmp_path / "nope.yaml")
    assert cfg.url_for() == "https://api.racebookhq.com/api/host/events/full"
