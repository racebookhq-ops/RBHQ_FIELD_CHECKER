"""The rendered-text fallback.

Synthetic token lists exercise the quirks; the real race page is checked
runner-by-runner against the JSON the same page loaded, so the two paths are
proven to agree.
"""

import pytest

from harness_scraper.fallback import FallbackError, parse_race_text, rendered_tokens
from harness_scraper.mapper import map_meeting

HEADER = ["No.", "Form", "Horse", "Trainer", "Driver", "Class", "Hcp", "Odds"]


def tokens(*runner_tokens):
    head = ["4", "3:33pm", "3h", "Leading Edge Pacers Band Handicap",
            "$9,120 4YO and older. No NR. RBD. Pacers Standing Start",
            "Track Record:", "LEAP TO FAME", "1:55.5", "2647m", "FIRST 4, 4TH LEG EARLY QUADRELLA"]
    out = head + HEADER
    for rt in runner_tokens:
        out += rt
    return out + ["Harness.org.au", "Help"]


def test_plain_runner_with_claim():
    race = parse_race_text(tokens(["1", "17621", "DRAGON", "Darrel Graham", "Tom Callaghan (C)", "NR80", "FR1", "10.00"]))
    [r] = race.runners
    assert (r.saddlecloth, r.form, r.horse, r.trainer) == (1, "17621", "DRAGON", "Darrel Graham")
    assert (r.driver, r.driver_claim, r.class_rating, r.handicap, r.odds, r.scratched) == \
        ("Tom Callaghan", "(C)", "NR80", "FR1", 10.0, False)


def test_status_token_between_horse_and_trainer_is_skipped():
    race = parse_race_text(tokens(["2", "47323", "PATH TO GREATNESS", "ODS", "Grant Dixon", "Jack Chapple", "NR104 B4", "10M", "3.60"]))
    r = race.runners[0]
    assert (r.horse, r.trainer, r.driver, r.class_rating, r.handicap, r.odds) == \
        ("PATH TO GREATNESS", "Grant Dixon", "Jack Chapple", "NR104 B4", "10M", 3.6)


def test_scratched_runner():
    race = parse_race_text(tokens(["7", "171s1", "FINAL DEADLINE NZ", "Shannon Price", "SCRATCHED", "NR120 B1", "30M", "SCR"]))
    r = race.runners[0]
    assert r.scratched and r.driver is None and r.odds is None and r.form == "171s1"


def test_form_containing_a_letter_and_a_form_that_is_only_digits():
    race = parse_race_text(tokens(
        ["1", "10s73", "ONE", "T One", "D One", "NR1", "FR1", "2.00"],
        ["2", "2", "TWO", "T Two", "D Two", "NR2", "FR2", "3.00"],      # form "2" must not be read as a saddlecloth
    ))
    assert [(r.saddlecloth, r.form, r.horse) for r in race.runners] == [(1, "10s73", "ONE"), (2, "2", "TWO")]


def test_runner_with_no_form_cell():
    race = parse_race_text(tokens(["1", "DEBUTANT", "T One", "D One", "NR1", "FR1", "2.00"]))
    assert race.runners[0].form is None and race.runners[0].horse == "DEBUTANT"


def test_race_header_fields():
    race = parse_race_text(tokens(["1", "1", "A", "B", "C", "NR1", "FR1", "2.00"]), race_id="APC06102601")
    assert (race.race_id, race.race_no, race.name) == ("APC06102601", 4, "Leading Edge Pacers Band Handicap")
    assert (race.prizemoney, race.start_type, race.class_text) == (9120, "standing", "4YO and older. No NR. RBD. Pacers")
    assert (race.track_record_horse, race.track_record_time, race.track_record_distance_m) == ("LEAP TO FAME", "1:55.5", 2647)
    assert race.bet_types == "FIRST 4, 4TH LEG EARLY QUADRELLA"
    assert race.parsed_from == "text"


def test_missing_grid_header_is_an_error_not_an_empty_race():
    with pytest.raises(FallbackError):
        parse_race_text(["JavaScript is not enabled"])


def test_header_labels_are_matched_case_insensitively():
    toks = tokens(["1", "1", "A", "B", "C", "NR1", "FR1", "2.00"])
    toks = [t.upper() if t in HEADER else t for t in toks]
    assert parse_race_text(toks).runners


# -- the real page, checked against the JSON it loaded --------------------------
def test_real_page_matches_its_own_api_json(harness_fixture):
    meta = harness_fixture("fixture_meta.json")
    expected = map_meeting(harness_fixture("race_api.json")).races[0]
    got = parse_race_text(harness_fixture("race_page.html"), race_id=meta["race_id"], race_no=meta["race_no"])

    assert len(got.runners) == len(expected.runners)
    for g, e in zip(got.runners, expected.runners):
        assert g.saddlecloth == e.saddlecloth
        assert g.horse.lower() == e.horse.lower()
        assert g.form == e.form
        assert g.trainer == e.trainer
        assert g.scratched == e.scratched
        assert g.class_rating == e.class_rating
        assert g.handicap.lower() == e.handicap.lower()
        assert g.odds == e.odds
        if not e.scratched:
            assert (g.driver, g.driver_claim) == (e.driver, e.driver_claim)


def test_real_page_race_header_matches_the_json(harness_fixture):
    meta = harness_fixture("fixture_meta.json")
    expected = map_meeting(harness_fixture("race_api.json")).races[0]
    got = parse_race_text(harness_fixture("race_page.html"), race_id=meta["race_id"])
    assert got.race_no == expected.race_no
    assert got.name == expected.name
    assert got.prizemoney == expected.prizemoney
    assert got.start_type == expected.start_type
    assert got.track_record_horse.lower() == expected.track_record_horse.lower()
    assert got.track_record_time == expected.track_record_time
    assert got.track_record_distance_m == expected.track_record_distance_m
    assert got.bet_types == expected.bet_types


def test_real_page_has_no_script_text_in_the_tokens(harness_fixture):
    toks = rendered_tokens(harness_fixture("race_page.html"))
    assert toks and not any("function(" in t or "window." in t for t in toks)
