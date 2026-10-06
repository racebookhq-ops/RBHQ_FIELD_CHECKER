"""Orchestration and output, with the browser replaced by the saved fixtures."""

import csv
import json
import re
from datetime import date

import pytest

from harness_scraper import scraper as scraper_mod
from harness_scraper.browser import Capture
from harness_scraper.config import Settings
from harness_scraper.exporters import write_csv, write_json
from harness_scraper.mapper import map_meeting, split_races
from harness_scraper.models import COLUMNS
from harness_scraper.scraper import HarnessScraper


class FakeBrowser:
    """Answers with the fixtures: the index, and the captured meeting's page."""

    def __init__(self, fx, meeting_json=True):
        self.fx, self.meeting_json = fx, meeting_json
        self.urls = []

    def __call__(self, settings):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def fetch(self, url, expect=None):
        self.urls.append(url)
        if "/racing/fields" in url:
            return Capture(url=url, status=200, html=self.fx("index.html"),
                           json={"https://api.harness.org.au/racing/fields?date=": self.fx("index_api.json")})
        meta = self.fx("fixture_meta.json")
        code = meta["meeting_code"]
        if url.endswith(f"/{code}/meeting/fields"):
            body = {f"https://api.harness.org.au/racing/{code}/": self.fx("meeting_api.json")} if self.meeting_json else {}
            return Capture(url=url, status=200, html="<html></html>", json=body)
        if url.endswith(f"/meeting/{meta['race_id']}/{meta['race_no']}/fields"):
            return Capture(url=url, status=200, html=self.fx("race_page.html"), json={})
        return Capture(url=url, status=200, html="<html></html>", json={})


@pytest.fixture
def setup(tmp_path, harness_fixture, monkeypatch):
    meta = harness_fixture("fixture_meta.json")
    state = map_meeting(harness_fixture("meeting_api.json")).state
    settings = Settings(data_dir=tmp_path / "data", log_dir=tmp_path / "logs", states=[state])
    day = date.fromisoformat(meta["date"])

    def make(meeting_json=True):
        fake = FakeBrowser(harness_fixture, meeting_json)
        monkeypatch.setattr(scraper_mod, "HarnessBrowser", fake)
        return fake

    return settings, day, meta, make


def test_scrape_day_from_meeting_json(setup):
    settings, day, meta, make = setup
    fake = make()
    card = HarnessScraper(settings).scrape_day(day)

    meeting = next(m for m in card.meetings if m.meeting_code == meta["meeting_code"])
    assert meeting.races and card.total_runners > 0
    # one page for the index, one per meeting - no race pages needed
    assert len(fake.urls) == 1 + len(card.meetings) + len([e for e in card.errors if e["stage"] == "meeting"])
    assert not any(re.search(r"/meeting/\w+/\d+/fields$", u) for u in fake.urls)


def test_raw_json_is_saved_per_race_and_replays_offline(setup):
    settings, day, meta, make = setup
    make()
    card = HarnessScraper(settings).scrape_day(day)

    raw = settings.raw_root / meta["date"]
    race_ids = {r.race_id for m in card.meetings for r in m.races}
    assert {p.stem for p in raw.glob("*.json")} == race_ids
    doc = json.loads((raw / f"{meta['race_id']}.json").read_text(encoding="utf-8"))
    assert len(doc["races"]) == 1 and doc["races"][0]["rise_race_code"] == meta["race_id"]

    replay = HarnessScraper(settings).scrape_from_raw(day)       # no browser involved
    assert replay.total_runners == card.total_runners
    assert [(m.meeting_code, [r.race_id for r in m.races]) for m in replay.meetings] == \
           [(m.meeting_code, [r.race_id for r in m.races]) for m in card.meetings]


def test_from_raw_with_nothing_saved_reports_it(setup):
    settings, day, _, _ = setup
    card = HarnessScraper(settings).scrape_from_raw(day)
    assert not card.meetings and card.errors


def test_falls_back_to_race_pages_when_meeting_json_is_missing(setup):
    settings, day, meta, make = setup
    make(meeting_json=False)
    card = HarnessScraper(settings).scrape_day(day)

    meeting = next(m for m in card.meetings if m.meeting_code == meta["meeting_code"])
    race = next(r for r in meeting.races if r.race_id == meta["race_id"])
    assert race.parsed_from == "text" and race.runners
    assert race.url.endswith(f"/meeting/{meta['race_id']}/{meta['race_no']}/fields")
    # the other races' pages were empty shells, so they are reported rather than invented
    assert any(e["stage"] == "race" for e in card.errors)


def test_state_filter_applies(setup):
    settings, day, meta, make = setup
    make()
    settings.states = ["TAS"] if settings.states != ["TAS"] else ["WA"]
    card = HarnessScraper(settings).scrape_day(day)
    assert all(m.meeting_code != meta["meeting_code"] for m in card.meetings)


# -- output ---------------------------------------------------------------------
@pytest.fixture
def card(harness_fixture):
    from harness_scraper.models import DayCard
    c = DayCard(meeting_date="2026-10-06", scraped_at="2026-10-06T12:00:00+11:00")
    c.meetings.append(map_meeting(harness_fixture("meeting_api.json")))
    return c


def test_csv_has_one_row_per_runner_with_meeting_and_race_repeated(card, tmp_path):
    path = write_csv(card, tmp_path / "harness")
    assert path == tmp_path / "harness" / "2026-10-06" / "fields.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == card.total_runners
    assert list(rows[0].keys()) == COLUMNS
    assert {r["meeting_code"] for r in rows} == {card.meetings[0].meeting_code}
    assert all(r["race_id"] and r["track_name"] and r["horse"] for r in rows)


def test_json_is_nested_meeting_race_runner(card, tmp_path):
    path = write_json(card, tmp_path / "harness")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "fields.json"
    assert "runners" not in data                       # runners live under their race
    [meeting] = data["meetings"]
    assert meeting["meeting_code"] == card.meetings[0].meeting_code
    assert set(meeting["track_layout"]) == {"circumference_m", "straight_length_m",
                                            "front_line_mobile", "front_line_standing"}
    race = meeting["races"][0]
    assert race["race_id"] and set(race["track_record"]) == {"horse", "time", "distance_m"}
    assert "track_name" not in race and "race_id" not in race["runners"][0]   # no repeated parents
    assert race["runners"][0]["horse"]
    assert sum(len(r["runners"]) for r in meeting["races"]) == data["summary"]["runners"] == card.total_runners


def test_nested_json_round_trips_and_old_flat_files_still_load(card, tmp_path):
    from harness_scraper.models import card_from_dict
    nested = card_from_dict(json.loads(write_json(card, tmp_path / "harness").read_text(encoding="utf-8")))
    assert nested.to_dict() == card.to_dict()

    flat = {"meeting_date": card.meeting_date, "scraped_at": "", "source": "x", "rows": None,
            "runners": card.rows()}
    legacy = card_from_dict(flat)
    assert legacy.total_runners == card.total_runners
    assert [r.race_no for r in legacy.meetings[0].races] == [r.race_no for r in card.meetings[0].races]


def test_split_races_documents_are_what_gets_replayed(harness_fixture):
    payload = harness_fixture("meeting_api.json")
    assert sum(len(map_meeting(d).races[0].runners) for d in split_races(payload)) == \
           sum(len(r.runners) for r in map_meeting(payload).races)
