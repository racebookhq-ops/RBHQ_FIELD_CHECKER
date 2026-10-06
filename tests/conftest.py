from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    """Return a Scrapling Selector over a saved HTML fixture, or skip the test."""
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"fixture {name} not present - run tools/dump_html.py first")
    from scrapling import Selector
    return Selector(content=path.read_text(encoding="utf-8"))


@pytest.fixture
def fixture_loader():
    return load_fixture


HARNESS_FIXTURES = FIXTURES / "harness"


def load_harness_fixture(name: str):
    """A harness fixture: parsed JSON for *.json, text otherwise. Skips when absent."""
    import json

    path = HARNESS_FIXTURES / name
    if not path.exists():
        pytest.skip(f"fixture harness/{name} not present - run tools/dump_harness.py first")
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


@pytest.fixture
def harness_fixture():
    return load_harness_fixture
