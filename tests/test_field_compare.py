"""Comparison tests.

Cards are built inline rather than from fixtures so each test states exactly
the one difference it is about, and the expected finding is unambiguous.
"""

from pathlib import Path

import pytest

from dogs_scraper.models import DayCard, Meeting, Race, Runner
from field_compare import Severity, compare_cards
from field_compare.matcher import load_aliases, match_cards
from field_compare.models import ComparisonReport
from field_compare.report import write_report

DAY = "2026-09-22"
BOXES = [("One Hot Chance", 1), ("Sutton Jet", 2), ("Take Flight", 3)]


def card(source, meetings):
    c = DayCard(meeting_date=DAY, scraped_at="2026-09-22T09:00:00+10:00", source=source)
    c.meetings.extend(meetings)
    return c


def meeting(track="Angle Park", slug="angle-park", races=(), **kw):
    m = Meeting(track=track, track_slug=slug, meeting_date=DAY, **kw)
    m.races.extend(races)
    return m


def race(number=1, runners=None, **kw):
    kw.setdefault("distance_m", 342)
    kw.setdefault("start_time_local", "2026-09-22T11:48:00+10:00")
    r = Race(race_number=number, name=f"Race {number}", **kw)
    r.runners.extend(runners if runners is not None else
                     [Runner(box=b, name=n) for n, b in BOXES])
    return r


def vacant(box):
    """A box with no dog in it, as both scrapers represent one."""
    return Runner(box=box, name=None, scratched=True, raw={"vacant": True})


def pair(ref_runners=None, our_runners=None, ref_race=None, our_race=None):
    """Two cards differing only in what is passed in."""
    reference = card("thedogs.com.au", [meeting(races=[ref_race or race(runners=ref_runners)])])
    ours = card("rbhq-api", [meeting(races=[our_race or race(runners=our_runners)])])
    return reference, ours


def types(report):
    return [d.type for d in report.sorted()]


# -- the happy path --------------------------------------------------------
def test_identical_cards_report_nothing():
    reference, ours = pair()
    report = compare_cards(reference, ours)

    assert report.discrepancies == []
    assert report.critical == []
    assert report.stats["meetings_matched"] == 1
    assert report.stats["races_compared"] == 1
    assert report.stats["runners_compared"] == 3
    assert report.stats["matched_on"] == "runner name"


def test_agreed_vacant_boxes_are_not_a_difference():
    runners = [Runner(box=1, name="One Hot Chance"), vacant(2), vacant(3)]
    reference, ours = pair(ref_runners=list(runners), our_runners=list(runners))
    assert compare_cards(reference, ours).discrepancies == []


def test_punctuation_in_names_is_not_a_difference():
    """O'Reilly's Boy and OReillys Boy are the same dog."""
    reference, ours = pair(
        ref_runners=[Runner(box=1, name="O'Reilly's Boy")],
        our_runners=[Runner(box=1, name="OREILLYS BOY")],
    )
    report = compare_cards(reference, ours)
    assert "wrong_dog_in_box" not in types(report)
    assert types(report) == ["name_spelling"]          # info only
    assert report.critical == []


# -- who is in the race ----------------------------------------------------
def test_a_dog_we_do_not_have_at_all():
    reference, ours = pair(
        ref_runners=[Runner(box=1, name="One Hot Chance"), Runner(box=2, name="Sutton Jet")],
        our_runners=[Runner(box=1, name="One Hot Chance")],
    )
    report = compare_cards(reference, ours)
    d = next(x for x in report.critical if x.type == "runner_missing")
    assert d.reference == "Sutton Jet"
    assert "we do not have it at all" in d.message


def test_a_dog_in_the_field_that_we_have_scratched():
    reference, ours = pair(
        ref_runners=[Runner(box=1, name="Sutton Jet")],
        our_runners=[Runner(box=1, name="Sutton Jet", scratched=True)],
    )
    report = compare_cards(reference, ours)
    d = next(x for x in report.critical if x.type == "runner_missing")
    assert "we have it scratched" in d.message


def test_a_dog_we_are_running_that_is_not_in_the_field():
    reference, ours = pair(
        ref_runners=[Runner(box=1, name="One Hot Chance")],
        our_runners=[Runner(box=1, name="One Hot Chance"), Runner(box=2, name="Ghost Dog")],
    )
    report = compare_cards(reference, ours)
    d = next(x for x in report.critical if x.type == "runner_not_in_field")
    assert d.ours == "Ghost Dog"


def test_a_dog_scratched_in_the_field_that_we_still_run():
    """The dangerous one - bets going on a scratching."""
    reference, ours = pair(
        ref_runners=[Runner(box=1, name="Take Flight", scratched=True)],
        our_runners=[Runner(box=1, name="Take Flight", scratched=False)],
    )
    report = compare_cards(reference, ours)
    assert [d.type for d in report.critical] == ["scratched_still_open"]


def test_both_sides_agree_a_dog_is_out():
    reference, ours = pair(
        ref_runners=[Runner(box=1, name="One Hot Chance"),
                     Runner(box=2, name="Take Flight", scratched=True)],
        our_runners=[Runner(box=1, name="One Hot Chance"),
                     Runner(box=2, name="Take Flight", scratched=True)],
    )
    assert compare_cards(reference, ours).discrepancies == []


def test_missing_meeting_and_race():
    reference = card("thedogs.com.au", [
        meeting(races=[race(1), race(2)]),
        meeting(track="Bulli", slug="bulli", races=[race(1)]),
    ])
    ours = card("rbhq-api", [meeting(races=[race(1)])])
    report = compare_cards(reference, ours)

    assert sorted(d.type for d in report.critical) == ["meeting_missing", "race_missing"]
    assert any(d.track == "Bulli" for d in report.critical)


# -- the box does not matter -----------------------------------------------
def test_the_same_dog_in_a_different_box_is_not_a_problem():
    """A promoted reserve wears a different rug on each side. Both are right."""
    reference, ours = pair(
        ref_runners=[Runner(box=9, name="Lazy Dynamite")],
        our_runners=[Runner(box=6, name="Lazy Dynamite")],
    )
    report = compare_cards(reference, ours)

    assert report.critical == []
    assert types(report) == ["box_mismatch"]
    assert report.discrepancies[0].severity is Severity.INFO


def test_two_dogs_swapping_boxes_is_not_a_problem():
    reference, ours = pair(
        ref_runners=[Runner(box=1, name="Sutton Jet"), Runner(box=2, name="Take Flight")],
        our_runners=[Runner(box=2, name="Sutton Jet"), Runner(box=1, name="Take Flight")],
    )
    report = compare_cards(reference, ours)
    assert report.critical == []
    assert all(d.type == "box_mismatch" for d in report.discrepancies)


def test_a_reserve_rug_still_counts_as_running():
    """Rug 9 on one side, box 7 on the other - the dog is in either way."""
    reference, ours = pair(
        ref_runners=[Runner(box=7, name="Nitro Ned")],
        our_runners=[Runner(box=10, name="Nitro Ned")],
    )
    assert compare_cards(reference, ours).critical == []


def test_a_dog_listed_twice_counts_as_running():
    """A promotion can leave the same name scratched and live on one card."""
    reference, ours = pair(
        ref_runners=[Runner(box=5, name="Just On Fire")],
        our_runners=[Runner(box=5, name="Just On Fire", scratched=True),
                     Runner(box=9, name="Just On Fire", scratched=False)],
    )
    assert compare_cards(reference, ours).critical == []


# -- warnings and info -----------------------------------------------------
def test_wrong_field_size_is_a_warning():
    """'race 1 is the wrong field' - counted on live runners, not boxes."""
    reference, ours = pair(
        ref_runners=[Runner(box=b, name=n) for n, b in BOXES],
        our_runners=[Runner(box=b, name=n) for n, b in BOXES[:2]],
    )
    report = compare_cards(reference, ours)
    size = next(d for d in report.discrepancies if d.type == "field_size_mismatch")
    assert (size.severity, size.reference, size.ours) == (Severity.WARNING, 3, 2)


def test_distance_mismatch_is_a_warning():
    reference, ours = pair(ref_race=race(distance_m=342), our_race=race(distance_m=395))
    report = compare_cards(reference, ours)
    d = next(x for x in report.discrepancies if x.type == "distance_mismatch")
    assert (d.severity, d.reference, d.ours) == (Severity.WARNING, 342, 395)


def test_start_time_drift_only_past_the_tolerance():
    same, _ = pair()
    near = card("rbhq-api", [meeting(races=[race(
        start_time_local="2026-09-22T11:49:00+10:00")])])        # 1 min
    far = card("rbhq-api", [meeting(races=[race(
        start_time_local="2026-09-22T11:58:00+10:00")])])        # 10 min

    assert "start_time_drift" not in types(compare_cards(same, near))
    drift = next(d for d in compare_cards(same, far).discrepancies
                 if d.type == "start_time_drift")
    assert drift.severity is Severity.INFO


def test_fields_missing_on_one_side_are_never_compared():
    """The feed has no weight, form, best time or odds - do not report them."""
    reference, ours = pair(
        ref_runners=[Runner(box=1, name="One Hot Chance", weight_kg=29.1,
                            form="20.10", best_time="19.73", odds=1.8)],
        our_runners=[Runner(box=1, name="One Hot Chance")],
    )
    report = compare_cards(reference, ours, strict=True)
    assert report.discrepancies == [], "a field only one side publishes is not a difference"


def test_trainer_only_compared_under_strict():
    reference, ours = pair(
        ref_runners=[Runner(box=1, name="One Hot Chance", trainer="Ruth Matic")],
        our_runners=[Runner(box=1, name="One Hot Chance", trainer="Someone Else")],
    )
    assert compare_cards(reference, ours).discrepancies == []
    strict = compare_cards(reference, ours, strict=True)
    assert types(strict) == ["trainer_mismatch"]
    assert strict.discrepancies[0].severity is Severity.INFO


# -- matching --------------------------------------------------------------
def test_tracks_pair_on_slug_despite_case():
    reference = card("thedogs.com.au", [meeting(track="Angle Park", slug="angle-park")])
    ours = card("rbhq-api", [meeting(track="Angle Park", slug="angle-park")])
    assert len(match_cards(reference, ours, {}).pairs) == 1


def test_alternate_venue_names_pair_a_track():
    """The feed ships its own aliases; the matcher uses them before the file."""
    reference = card("thedogs.com.au", [meeting(track="Ladbrokes Q1 Lakeside",
                                                slug="ladbrokes-q1-lakeside")])
    ours = card("rbhq-api", [meeting(track="Q1 Lakeside", slug="q1-lakeside",
                                     raw={"alternate_names": ["Ladbrokes Q1 Lakeside"]})])
    assert len(match_cards(reference, ours, {}).pairs) == 1


def test_alias_file_pairs_a_track():
    aliases = load_aliases()
    reference = card("thedogs.com.au", [meeting(track="Ladbrokes Q1 Lakeside",
                                                slug="ladbrokes-q1-lakeside")])
    ours = card("rbhq-api", [meeting(track="Q1 Lakeside", slug="q1-lakeside")])
    assert len(match_cards(reference, ours, aliases).pairs) == 1


def test_unmatched_tracks_are_reported_with_both_spellings():
    reference = card("thedogs.com.au", [meeting(track="Goulburn", slug="goulburn")])
    ours = card("rbhq-api", [meeting(track="Gouburn Park", slug="gouburn-park")])
    report = compare_cards(reference, ours, aliases={})

    unmatched = report.stats["unmatched"]
    assert unmatched["reference_only"] == [{"track": "Goulburn", "slug": "goulburn"}]
    assert unmatched["ours_only"] == [{"track": "Gouburn Park", "slug": "gouburn-park"}]


# -- the report an agent reads ---------------------------------------------
def test_criticals_sort_first():
    reference, ours = pair(
        ref_runners=[Runner(box=1, name="One Hot Chance"), Runner(box=2, name="Sutton Jet")],
        our_runners=[Runner(box=2, name="One Hot Chance"), Runner(box=3, name="Take Flight")],
    )
    report = compare_cards(reference, ours)
    severities = [d.severity for d in report.sorted()]
    assert severities[0] is Severity.CRITICAL
    assert severities == sorted(severities, key=lambda s: ["critical", "warning", "info"].index(s.value))


def test_report_serialises_for_an_agent(tmp_path):
    reference, ours = pair(
        ref_runners=[Runner(box=2, name="Sutton Jet")],
        our_runners=[Runner(box=2, name="Take Flight")],
    )
    report = compare_cards(reference, ours)
    path = write_report(report, tmp_path)

    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == f"discrepancies_{DAY}.json"
    assert set(data) == {"meeting_date", "generated_at", "reference_source",
                         "our_source", "summary", "discrepancies"}
    # One dog in the field we do not have, one we run that is not in it.
    assert data["summary"]["counts"] == {"critical": 2, "warning": 0, "info": 0}
    assert data["our_source"] == "rbhq-api"

    first = data["discrepancies"][0]
    assert first["severity"] == "critical"
    # every record carries the dog and where to look, so the agent need not
    # re-read either source
    assert first["reference"] == "Sutton Jet"
    assert "null" not in json.dumps(first), "records should omit keys that do not apply"

def test_a_sponsor_prefix_does_not_stop_a_track_pairing():
    """thedogs calls it "Ladbrokes Q Straight"; the feed calls it "Q Straight"."""
    reference = card("thedogs.com.au", [meeting(track="Ladbrokes Q Straight",
                                                slug="ladbrokes-q-straight")])
    ours = card("rbhq-api", [meeting(track="Q Straight", slug="q-straight")])
    assert len(match_cards(reference, ours, {}).pairs) == 1


def test_stripping_a_prefix_does_not_merge_different_tracks():
    reference = card("thedogs.com.au", [meeting(track="Ladbrokes", slug="ladbrokes")])
    ours = card("rbhq-api", [meeting(track="Gosford", slug="gosford")])
    assert match_cards(reference, ours, {}).pairs == []
