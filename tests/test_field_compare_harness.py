"""Harness field comparison: RBHQ (ours) against harness.org.au (reference)."""

import copy
import json

import pytest

from field_compare.cli import main
from field_compare.harness import compare_harness, horse_key
from field_compare.matcher import load_aliases
from harness_scraper.mapper import map_meeting
from harness_scraper.models import DayCard, Meeting, Race, Runner, card_from_dict


def race(no, *horses, scratched=()):
    return Race(race_id=f"R{no}", race_no=no, runners=[
        Runner(saddlecloth=i + 1, horse=h, scratched=h in scratched) for i, h in enumerate(horses)])


def card(*meetings, source="x"):
    return DayCard(meeting_date="2026-10-06", scraped_at="", source=source, meetings=list(meetings))


def meeting(name, *races):
    return Meeting(date="2026-10-06", track_name=name, track_slug=name.lower().replace(" ", "-"),
                   races=list(races))


def types(report):
    return sorted(d.type for d in report.discrepancies)


def base():
    return meeting("Menangle", race(1, "Alpha", "Bravo"), race(2, "Charlie", "Delta"))


# -- the field matches ----------------------------------------------------------
def test_identical_cards_have_no_findings():
    r = compare_harness(card(base()), card(base()))
    assert r.discrepancies == []
    assert r.stats["races_compared"] == 2 and r.stats["runners_compared"] == 4


def test_names_ignore_case_punctuation_and_country_tag():
    assert horse_key("FINAL DEADLINE NZ") == horse_key("Final Deadline") == horse_key("Final Deadline (NZ)")
    assert horse_key("O'Reilly's Boy") == horse_key("OREILLYS BOY")
    ref = card(meeting("Menangle", race(1, "Final Deadline NZ")))
    ours = card(meeting("MENANGLE", race(1, "FINAL DEADLINE")))
    assert compare_harness(ref, ours).discrepancies == []


# -- 1. the race exists -----------------------------------------------------------
def test_we_have_a_race_the_official_site_does_not():
    ref = meeting("Menangle", *(race(n, "A%d" % n) for n in range(1, 9)))
    ours = meeting("Menangle", *ref.races, race(9, "Echo"))
    [d] = compare_harness(card(ref), card(ours)).discrepancies
    assert (d.type, d.severity.value, d.race_number) == ("race_unexpected", "critical", 9)
    assert "stops at R8" in d.message


def test_official_race_missing_from_ours():
    ours = meeting("Menangle", race(1, "Alpha", "Bravo"))
    [d] = compare_harness(card(base()), card(ours)).discrepancies
    assert (d.type, d.severity.value, d.race_number) == ("race_missing", "critical", 2)


def test_runners_of_an_unpaired_race_are_not_reported_one_by_one():
    ours = base()
    ours.races.append(race(9, "Echo", "Foxtrot"))
    assert types(compare_harness(card(base()), card(ours))) == ["race_unexpected"]


# -- 2. the runner is in the field --------------------------------------------------
def test_runner_missing_and_runner_not_in_field():
    ours = meeting("Menangle", race(1, "Alpha", "Zulu"), race(2, "Charlie", "Delta"))
    report = compare_harness(card(base()), card(ours))
    assert types(report) == ["runner_missing", "runner_not_in_field"]
    assert all(d.severity.value == "critical" for d in report.discrepancies)
    missing = next(d for d in report.discrepancies if d.type == "runner_missing")
    assert missing.reference == "Bravo" and missing.ours is None
    assert missing.race_number == 1


def test_scratchings_are_compared_by_activity():
    ref = card(meeting("Menangle", race(1, "Alpha", "Bravo", scratched={"Bravo"})))
    ours_open = card(meeting("Menangle", race(1, "Alpha", "Bravo")))
    assert types(compare_harness(ref, ours_open)) == ["scratched_still_open"]

    ref2 = card(meeting("Menangle", race(1, "Alpha", "Bravo")))
    ours_scr = card(meeting("Menangle", race(1, "Alpha", "Bravo", scratched={"Bravo"})))
    [d] = compare_harness(ref2, ours_scr).discrepancies
    assert d.type == "runner_missing" and "scratched" in d.message

    both = card(meeting("Menangle", race(1, "Alpha", "Bravo", scratched={"Bravo"})))
    assert compare_harness(both, copy.deepcopy(both)).discrepancies == []


def test_a_name_with_its_last_word_dropped_is_one_name_mismatch():
    ref = card(meeting("Canberra", race(4, "Pencil Me In", "Alpha")))
    ours = card(meeting("Canberra", race(4, "Pencil Me", "Alpha")))
    [d] = compare_harness(ref, ours).discrepancies
    assert (d.type, d.severity.value) == ("name_mismatch", "warning")
    assert (d.reference, d.ours, d.race_number) == ("Pencil Me In", "Pencil Me", 4)


def test_unrelated_names_are_still_missing_plus_extra():
    ref = card(meeting("Canberra", race(4, "Pencil Me In")))
    ours = card(meeting("Canberra", race(4, "Zulu")))
    assert types(compare_harness(ref, ours)) == ["runner_missing", "runner_not_in_field"]


# -- 3. the runner is in the correct race --------------------------------------------
def test_runner_in_the_wrong_race_is_one_finding_not_two():
    ref = card(meeting("Menangle", race(1, "Alpha"), race(2, "Bravo"), race(3, "Charlie")))
    ours = card(meeting("Menangle", race(1, "Alpha"), race(2, "Charlie"), race(3, "Bravo")))
    report = compare_harness(ref, ours)
    assert types(report) == ["wrong_race", "wrong_race"]
    msgs = {d.message for d in report.discrepancies}
    assert any("Charlie is in R2 on ours but in R3" in m for m in msgs)
    assert any("Bravo is in R3 on ours but in R2" in m for m in msgs)


def test_wrong_race_when_our_race_is_the_extra_one():
    ref = card(meeting("Menangle", *(race(n, f"H{n}") for n in range(1, 9))))
    ours = card(meeting("Menangle", *(race(n, f"H{n}") for n in range(1, 8)), race(9, "H8")))
    report = compare_harness(ref, ours)
    assert types(report) == ["race_missing", "race_unexpected", "wrong_race"]
    wrong = next(d for d in report.discrepancies if d.type == "wrong_race")
    assert wrong.race_number == 9 and wrong.reference == [8] and wrong.ours == 9


def test_a_scratched_horse_in_another_race_is_not_a_wrong_race():
    ref = card(meeting("Menangle", race(1, "Alpha", "Bravo"), race(2, "Charlie")))
    ours = card(meeting("Menangle", race(1, "Alpha"), race(2, "Charlie", "Bravo", scratched={"Bravo"})))
    assert types(compare_harness(ref, ours)) == ["runner_missing"]


# -- meetings ---------------------------------------------------------------------
def test_meeting_pairing_and_unmatched():
    ref = card(meeting("Menangle", race(1, "A")), meeting("Bathurst", race(1, "B")))
    ours = card(meeting("MENANGLE", race(1, "A")), meeting("Tamworth", race(1, "C")))
    report = compare_harness(ref, ours)
    assert types(report) == ["meeting_missing", "meeting_unexpected"]
    assert report.stats["unmatched"]["reference_only"][0]["track"] == "Bathurst"


def test_track_alias_pairs_a_differently_spelled_venue(tmp_path):
    path = tmp_path / "a.yaml"
    path.write_text("gloucester-park:\n  - GLOUCESTER PK\n", encoding="utf-8")
    ref = card(meeting("Gloucester Park", race(1, "A")))
    ours = card(meeting("GLOUCESTER PK", race(1, "A")))
    assert types(compare_harness(ref, ours)) == ["meeting_missing", "meeting_unexpected"]
    assert compare_harness(ref, ours, aliases=load_aliases(path)).discrepancies == []


# -- against the real captured meeting ----------------------------------------------
@pytest.fixture
def real(harness_fixture):
    return card(map_meeting(harness_fixture("meeting_api.json")), source="harness.org.au")


def test_real_meeting_matches_itself_after_a_save_and_reload(real):
    reloaded = card_from_dict(json.loads(json.dumps(real.to_dict())))
    assert reloaded.total_runners == real.total_runners
    assert compare_harness(real, reloaded).discrepancies == []


def test_real_meeting_catches_each_kind_of_damage(real):
    ours = card_from_dict(real.to_dict())
    races = ours.meetings[0].races
    races.pop()                                                  # a race we lack
    victim = next(r for r in races[0].runners if not r.scratched)
    victim.horse = "Not A Real Horse"                            # wrong name -> missing + extra
    races.append(Race(race_id="X9", race_no=99, runners=[Runner(saddlecloth=1, horse="Ghost")]))
    report = compare_harness(real, ours)
    assert {"race_missing", "race_unexpected", "runner_missing", "runner_not_in_field"} <= set(types(report))


# -- CLI replay ---------------------------------------------------------------------
def rbhq_payload(c):
    """An RBHQ-shaped harness response for a harness card."""
    meetings = []
    for m in c.meetings:
        meetings.append({
            "meetingId": 1, "meetingDate": f"{m.date}T00:00:00.000Z", "venue": m.track_name.upper(),
            "type": "H", "country": "AU", "state": m.state,
            "events": [{"eventId": r.race_id, "eventNumber": r.race_no, "eventName": r.name,
                        "startTime": "2026-10-06T02:00:00.000Z", "Runners": [
                            {"runnerNumber": u.saddlecloth, "name": u.horse, "scratched": u.scratched,
                             "trainer": u.trainer, "jockey": u.driver} for u in r.runners]}
                       for r in m.races]})
    return {"successful": True, "meetings": meetings}


@pytest.mark.parametrize("damage, code", [(False, 0), (True, 1)])
def test_cli_replay(real, tmp_path, damage, code):
    payload = rbhq_payload(real)
    if damage:
        payload["meetings"][0]["events"].append(
            {"eventId": "X9", "eventNumber": 99, "Runners": [{"runnerNumber": 1, "name": "Ghost"}]})
    ref, ours = tmp_path / "fields.json", tmp_path / "raw_h.json"
    ref.write_text(json.dumps(real.to_dict()), encoding="utf-8")
    ours.write_text(json.dumps(payload), encoding="utf-8")

    out = tmp_path / "data"
    day = real.meetings[0].date
    rc = main(["--harness", "--date", day, "--reference-file", str(ref),
               "--ours-file", str(ours), "--output-dir", str(out)])
    assert rc == code
    report = json.loads((out / "harness" / day / "discrepancies.json").read_text(encoding="utf-8"))
    assert report["summary"]["counts"]["critical"] == (1 if damage else 0)


def test_cli_refuses_to_report_when_our_side_is_empty(real, tmp_path, capsys):
    ref, ours = tmp_path / "fields.json", tmp_path / "raw_h.json"
    ref.write_text(json.dumps(real.to_dict()), encoding="utf-8")
    ours.write_text(json.dumps({"successful": True, "meetings": []}), encoding="utf-8")
    out = tmp_path / "data"
    rc = main(["--harness", "--date", real.meetings[0].date, "--reference-file", str(ref),
               "--ours-file", str(ours), "--output-dir", str(out)])
    assert rc == 2
    assert "no harness meetings" in capsys.readouterr().out
    assert not list(out.rglob("discrepancies.json"))
