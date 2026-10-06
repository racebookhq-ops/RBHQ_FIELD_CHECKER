"""Mapping tests for the RBHQ feed.

The fixture is a trimmed excerpt of a real response, kept small but chosen to
contain every case the mapper has to reason about:

    Angle Park R1  vacant boxes 3 and 6, a scratching in box 8 with no
                   replacement, and two reserves holding barrier 0
    Angle Park R3  a reserve promoted into box 5 over a scratched dog
    Mandurah R1    a clean 8-box field with one vacant box (a different state)
    Monmore R3     a GB meeting on the previous day (filtered out by default)
"""

from datetime import date
from pathlib import Path

import pytest

from dogs_scraper.models import card_from_dict
from rbhq_scraper.client import FeedError, load_file
from rbhq_scraper.mapper import build_card, is_vacant, meeting_day, utc_to_local

FIXTURE = Path(__file__).parent / "fixtures" / "rbhq_response.json"
DAY = date(2026, 9, 22)


@pytest.fixture
def payload():
    return load_file(FIXTURE)


@pytest.fixture
def card(payload):
    return build_card(payload, DAY)


def _race(card, track, number):
    meeting = next(m for m in card.meetings if m.track == track)
    return next(r for r in meeting.races if r.race_number == number)


# -- helpers ---------------------------------------------------------------
def test_vacant_box_marker_is_recognised():
    assert is_vacant("....")
    assert is_vacant(" ... ")
    assert not is_vacant("Alia Rose")
    assert not is_vacant("")
    assert not is_vacant(None)


def test_start_times_convert_to_sydney():
    # The feed is UTC; thedogs publishes every start in Australia/Sydney.
    assert utc_to_local("2026-09-22T01:10:00.000Z") == "2026-09-22T11:10:00+10:00"
    assert utc_to_local(None) is None
    assert utc_to_local("not a timestamp") is None


def test_meeting_day_is_not_timezone_shifted():
    """midnight-UTC stands in for a calendar day - converting would roll it back."""
    assert meeting_day("2026-09-22T00:00:00.000Z") == "2026-09-22"


# -- scope -----------------------------------------------------------------
def test_offshore_and_other_days_are_excluded_by_default(card):
    assert [m.track for m in card.meetings] == ["Angle Park", "Mandurah"]
    assert card.meeting_date == "2026-09-22"
    assert card.source == "rbhq-api"


def test_other_countries_can_be_opted_into(payload):
    card = build_card(payload, date(2026, 9, 21), countries=("AU", "GB"))
    assert [m.track for m in card.meetings] == ["Monmore"]


def test_non_greyhound_meetings_are_dropped():
    card = build_card({"meetings": [
        {"meetingId": 1, "meetingDate": "2026-09-22T00:00:00.000Z", "venue": "RANDWICK",
         "type": "T", "country": "AU", "state": "NSW",
         "events": [{"eventNumber": 1, "Runners": []}]},
    ]}, DAY)
    assert card.meetings == []


def test_state_and_track_filters(payload):
    assert [m.track for m in build_card(payload, DAY, states=["WA"]).meetings] == ["Mandurah"]
    assert [m.track for m in build_card(payload, DAY, tracks=["angle-park"]).meetings] == ["Angle Park"]


# -- meetings and races ----------------------------------------------------
def test_meeting_fields(card):
    meeting = next(m for m in card.meetings if m.track == "Angle Park")
    assert meeting.track_slug == "angle-park"
    assert meeting.state == "SA"           # the feed publishes state; the scraper cannot
    assert meeting.meeting_date == "2026-09-22"
    assert meeting.raw["meeting_id"] == 1514454
    assert meeting.raw["alternate_names"] == ["Angle Park Night"]
    # The fixture keeps 2 of the meeting's 14 races, and says so.
    assert meeting.raw["events_published"] == 14


def test_race_fields(card):
    race = _race(card, "Angle Park", 1)
    assert race.name == "14 Races @ Angle Park Today Maiden Final"
    assert race.distance_m == 342          # 342.0 in the feed
    assert race.grade == "Maiden"
    assert race.start_time_local == "2026-09-22T11:10:00+10:00"
    assert race.raw["event_id"] == "1514454-1"
    assert race.raw["status"] == "DONE"


def test_races_come_back_in_number_order(card):
    for meeting in card.meetings:
        numbers = [r.race_number for r in meeting.races]
        assert numbers == sorted(numbers)


# -- the box is the whole point --------------------------------------------
def test_box_comes_from_barrier_not_runner_number(card):
    """runnerNumber counts past the field into the reserves; barrier is the rug."""
    race = _race(card, "Angle Park", 1)
    assert [r.box for r in race.runners if r.box] == [1, 2, 3, 4, 5, 6, 7, 8]

    box_one = race.runners[0]
    assert box_one.name == "Whiplash Emmett"
    assert box_one.raw["runner_number"] == 1


def test_reserves_are_kept_as_runners_without_a_box(card):
    """A reserve is still a greyhound that may be running.

    Dropping barrier-0 entries hid them from the comparison, which then
    reported them as dogs in the field we did not have at all. They come
    through with no box and a `reserve` flag instead.
    """
    race = _race(card, "Angle Park", 1)
    reserves = [r for r in race.runners if r.raw.get("reserve")]

    assert [r.name for r in reserves] == ["Adhana Tori", "Adhana Remi"]
    assert all(r.box is None for r in reserves), "a reserve must not invent a box 0"
    # ...and they are still on the card, not filed away out of sight.
    assert {"Adhana Tori", "Adhana Remi"} <= {r.name for r in race.runners}


def test_an_unscratched_reserve_is_not_lost(payload):
    """The bug this guards: runner 9 or 10 on barrier 0, still in the race."""
    import copy
    tweaked = copy.deepcopy(payload)
    event = tweaked["meetings"][0]["events"][0]
    reserve = next(r for r in event["Runners"] if r["runnerNumber"] == 9)
    reserve["scratched"] = False
    reserve["scratchingTimestamp"] = None

    race = _race(build_card(tweaked, DAY), "Angle Park", 1)
    live = [r.name for r in race.runners if not r.scratched]
    assert "Adhana Tori" in live


def test_vacant_boxes_are_kept_and_flagged(card):
    """An empty box survives as a scratching, exactly as in the dogs scraper."""
    race = _race(card, "Angle Park", 1)
    vacant = [r for r in race.runners if r.raw.get("vacant")]

    assert [r.box for r in vacant] == [3, 6]
    assert all(r.name is None for r in vacant), "an empty box holds no dog name"
    assert all(r.scratched for r in vacant)


def test_scratched_dog_keeps_its_name(card):
    """Box 8 was scratched with nobody promoted in - the dog is still named."""
    race = _race(card, "Angle Park", 1)
    box_eight = next(r for r in race.runners if r.box == 8)

    assert box_eight.name == "Get Them Jimmy"
    assert box_eight.scratched is True
    assert box_eight.scratch_time == "2026-09-21T19:47:01.570000+10:00"
    assert not box_eight.raw.get("vacant")


def test_both_halves_of_a_promotion_are_reported(card):
    """Box 5 held a scratched dog and the reserve that replaced it.

    Both are kept: collapsing them to one lost the dog that came out.
    """
    race = _race(card, "Angle Park", 3)
    box_five = [r for r in race.runners if r.box == 5]

    assert sorted(r.name for r in box_five) == ["Brooklyn", "Just On Fire"]
    assert {r.name: r.scratched for r in box_five} == {
        "Brooklyn": True, "Just On Fire": False}


def test_runners_come_back_in_box_order_with_reserves_last(card):
    for meeting in card.meetings:
        for race in meeting.races:
            boxed = [r.box for r in race.runners if r.box]
            assert boxed == sorted(boxed), "boxed runners should be in box order"
            unboxed = [i for i, r in enumerate(race.runners) if r.box is None]
            if unboxed:
                assert min(unboxed) > max(
                    i for i, r in enumerate(race.runners) if r.box),                     "reserves belong at the end of the card"


def test_field_size_and_scratchings(card):
    """The derived fields the comparison actually reads."""
    r1 = _race(card, "Angle Park", 1)
    assert r1.field_size == 5            # 8 boxes, less 2 vacant and 1 scratching
    assert r1.scratchings == [3, 6, 8]

    r3 = _race(card, "Angle Park", 3)
    assert r3.field_size == 6            # box 5 refilled by the reserve
    # Box 5 lists both the dog that came out and the one that went in.
    assert r3.scratchings == [3, 5, 6]

    mandurah = _race(card, "Mandurah", 1)
    assert mandurah.field_size == 7
    assert mandurah.scratchings == [5]


# -- output shape ----------------------------------------------------------
def test_unavailable_fields_are_null_not_invented(card):
    """The feed has no weight, form, best time or price - do not guess them."""
    for meeting in card.meetings:
        for race in meeting.races:
            for runner in race.runners:
                assert runner.weight_kg is None
                assert runner.form is None
                assert runner.best_time is None
                assert runner.odds is None


def test_card_serialises_to_the_dogs_scraper_shape(card):
    """Same keys, and it survives a round trip through card_from_dict."""
    data = card.to_dict()
    assert set(data) == {"meeting_date", "scraped_at", "source", "summary",
                         "meetings", "errors"}
    assert set(data["summary"]) == {"meetings", "races", "runners", "errors"}

    race = data["meetings"][0]["races"][0]
    for key in ("race_number", "name", "distance_m", "grade", "start_time_local",
                "prize_money", "track_condition", "comment", "url",
                "field_size", "scratchings", "runners"):
        assert key in race

    reloaded = card_from_dict(data)
    assert reloaded.to_dict() == data


# -- client ----------------------------------------------------------------
def test_wrong_payload_shape_is_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"results": []}', encoding="utf-8")
    with pytest.raises(FeedError, match="no 'meetings' key"):
        load_file(bad)

    with pytest.raises(FeedError, match="no such file"):
        load_file(tmp_path / "missing.json")
