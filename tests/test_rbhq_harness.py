"""RBHQ harness mapping.

NO REAL HARNESS RESPONSE EXISTS YET. These payloads reuse the real greyhound
fixture's envelope (the feed shares one shape across race types) with the type
switched to "H", so they prove the plumbing - filtering, ordering, time zone,
CLI wiring - and NOT that the feed fills these keys the way the mapper assumes.
Replace with a real capture (`python -m rbhq_scraper --harness --save-response`).
"""

import copy
import csv
import json
from datetime import date
from pathlib import Path

import pytest

from rbhq_scraper.cli import main
from rbhq_scraper.client import load_file
from rbhq_scraper.harness_mapper import build_harness_card
from rbhq_scraper.mapper import build_card

FIXTURE = Path(__file__).parent / "fixtures" / "rbhq_response.json"
DAY = date(2026, 9, 22)


@pytest.fixture
def payload():
    p = copy.deepcopy(load_file(FIXTURE))
    for m in p["meetings"]:
        m["type"] = "H"
        for e in m["events"]:
            e["type"] = "H"
            for r in e["Runners"]:
                r["jockey"] = "Test Driver"
    return p


def test_only_harness_meetings_are_mapped(payload):
    payload["meetings"][0]["type"] = "G"
    card = build_harness_card(payload, DAY)
    assert card.source == "rbhq-api"
    assert all(m.track_name != "Angle Park" for m in card.meetings)
    assert card.meetings                                    # Mandurah (AU, H) remains


def test_greyhound_mapper_ignores_harness_meetings(payload):
    assert build_card(payload, DAY).meetings == []


def test_fields_map_and_times_are_sydney(payload):
    card = build_harness_card(payload, DAY)
    m = next(m for m in card.meetings if m.track_name == "Angle Park")
    assert (m.date, m.state, m.track_slug) == ("2026-09-22", "SA", "angle-park")
    race = m.races[0]
    assert (race.race_no, race.race_id, race.distance_m) == (1, "1514454-1", 342)
    assert race.start_time == "2026-09-22T11:10:00+10:00"
    assert race.bet_types == "Win, Place"
    r = race.runners[0]
    assert (r.saddlecloth, r.horse, r.trainer, r.driver) == (1, "Whiplash Emmett", "Kym Burnett", "Test Driver")
    assert r.handicap is None and r.odds is None            # not in the feed


def test_country_and_day_filters(payload):
    assert all(m.track_name != "Monmore" for m in build_harness_card(payload, DAY).meetings)
    assert build_harness_card(payload, date(2026, 9, 23)).meetings == []


def test_cli_replays_a_saved_file_and_writes_rbhq_fields(payload, tmp_path):
    src = tmp_path / "raw_h.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "out"
    code = main(["--harness", "--file", str(src), "--date", "2026-09-22", "--output-dir", str(out)])
    assert code == 0
    rows = list(csv.DictReader((out / "harness" / "2026-09-22" / "rbhq_fields.csv").open(encoding="utf-8")))
    assert rows and rows[0]["horse"] and rows[0]["saddlecloth"]
    assert (out / "harness" / "2026-09-22" / "rbhq_fields.json").exists()
