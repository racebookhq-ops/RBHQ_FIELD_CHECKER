"""JSON -> model mapping.

The synthetic cases only use keys seen in a real capture (6 Oct 2026). The
fixture cases map the real files saved by tools/dump_harness.py.
"""

from datetime import datetime

from harness_scraper.mapper import map_meeting, map_race, map_runner, split_races, to_sydney_iso


def runner(**over):
    base = {
        "saddlecloth_number": 3, "barrier": "Fr3", "formatted_handicap": "Fr3",
        "is_scratching": False, "driver_concession_flags": None,
        "woo_average_odds": "2.60", "forecast_odds": "3.20",
        "horse": {"id": 1, "name": "Second To Nun", "slug": "/second-to-nun"},
        "trainer": {"display_name": "Stephen Cini"},
        "driver": {"display_name": "Pete McMullen"},
        "stats_at_race_time": {"last_five_starts_form": "37418", "horse_class": "NR60"},
    }
    base.update(over)
    return base


# -- runner --------------------------------------------------------------------
def test_runner_fields():
    r = map_runner(runner())
    assert (r.saddlecloth, r.horse, r.form, r.trainer, r.driver) == (3, "Second To Nun", "37418", "Stephen Cini", "Pete McMullen")
    assert (r.class_rating, r.handicap, r.scratched, r.driver_claim) == ("NR60", "Fr3", False, None)


def test_odds_is_the_displayed_column_not_the_forecast():
    assert map_runner(runner()).odds == 2.6
    assert map_runner(runner(woo_average_odds=None)).odds is None


def test_driver_claim_is_kept_apart_from_the_name():
    r = map_runner(runner(driver_concession_flags="(C,5)"))
    assert (r.driver, r.driver_claim) == ("Pete McMullen", "(C,5)")


def test_scratched_flag():
    assert map_runner(runner(is_scratching=True)).scratched is True


# -- race / meeting ------------------------------------------------------------
def race_doc(**over):
    doc = {
        "rise_race_code": "APC06102613", "race_number": 1, "name": "Pryde's Easifeed Energy Pak",
        "distance": 2138, "start_type": "MS", "bet_types": "FIRST 4",
        "scheduled_start_time": "2026-10-06T13:45:00+11:00",
        "race_class": "NR up to 55. RBD. Trotters", "race_notes": "NDC.", "race_status": "fields_drawn",
        "total_prize_money": 9120,
        "track_record": {"horse_name": "Aldebaranstilinski", "time_mile_rate": "1:54.9", "distance": 2138},
        "runners": [runner(saddlecloth_number=2), runner(saddlecloth_number=1)],
    }
    doc.update(over)
    return doc


def test_race_fields_and_runner_order():
    race = map_race(race_doc())
    assert (race.race_id, race.race_no, race.distance_m, race.prizemoney) == ("APC06102613", 1, 2138, 9120)
    assert (race.start_type, race.bet_types, race.status) == ("mobile", "FIRST 4", "fields_drawn")
    assert (race.track_record_horse, race.track_record_time, race.track_record_distance_m) == ("Aldebaranstilinski", "1:54.9", 2138)
    assert [r.saddlecloth for r in race.runners] == [1, 2]


def test_start_types():
    assert map_race(race_doc(start_type="SS")).start_type == "standing"
    assert map_race(race_doc(start_type="XX")).start_type == "XX"       # unknown codes pass through
    assert map_race(race_doc(start_type=None)).start_type is None


def test_missing_track_record_is_fine():
    race = map_race(race_doc(track_record=None))
    assert race.track_record_horse is None and race.track_record_time is None


def test_start_time_is_converted_to_sydney():
    # Gloucester Park runs on AWST (+08:00); Sydney is +11:00 in October
    assert to_sydney_iso("2026-10-06T18:30:00+08:00") == "2026-10-06T21:30:00+11:00"
    assert to_sydney_iso("2026-10-06T13:45:00+11:00") == "2026-10-06T13:45:00+11:00"
    assert to_sydney_iso(None) is None and to_sydney_iso("nonsense") is None


def test_meeting_fields():
    payload = {
        "rise_meeting_code": "AP061026", "date": "2026-10-06", "is_trial": False,
        "track": {"slug": "/albion-park", "desktop_display_name": "Albion Park", "state": "qld",
                  "circumference": 1019.0, "home_straight_length": 197.0,
                  "max_front_row_mobile": 7, "max_row_standing": 8},
        "races": [race_doc(race_number=2), race_doc(race_number=1)],
    }
    m = map_meeting(payload)
    assert (m.track_name, m.track_slug, m.state, m.meeting_code, m.date) == ("Albion Park", "albion-park", "QLD", "AP061026", "2026-10-06")
    assert (m.circumference_m, m.straight_length_m, m.front_line_mobile, m.front_line_standing) == (1019, 197, 7, 8)
    assert m.is_trial is False
    assert [r.race_no for r in m.races] == [1, 2]
    assert m.races[0].url == "https://www.harness.org.au/racing/2026-10-06/albion-park/AP061026/meeting/APC06102613/1/fields"


# -- real captures -------------------------------------------------------------
def test_real_meeting_maps_fully(harness_fixture):
    meta = harness_fixture("fixture_meta.json")
    m = map_meeting(harness_fixture("meeting_api.json"))
    assert m.meeting_code == meta["meeting_code"] and m.date == meta["date"]
    assert m.state and m.track_name and m.track_slug
    assert m.circumference_m and m.straight_length_m
    assert m.races
    for race in m.races:
        assert race.race_id and race.race_no and race.distance_m
        assert race.start_time and datetime.fromisoformat(race.start_time).utcoffset() is not None
        assert race.start_type in ("mobile", "standing")
        assert race.runners
        cloths = [r.saddlecloth for r in race.runners]
        assert len(cloths) == len(set(cloths)), "duplicate saddlecloths"
        assert all(r.horse for r in race.runners)


def test_real_meeting_has_races_out_of_id_order_or_at_least_ids_come_from_json(harness_fixture):
    m = map_meeting(harness_fixture("meeting_api.json"))
    assert len({r.race_id for r in m.races}) == len(m.races)
    assert [r.race_no for r in m.races] == sorted(r.race_no for r in m.races)


def test_real_single_race_response_is_the_same_shape_as_a_meeting(harness_fixture):
    meta = harness_fixture("fixture_meta.json")
    single = map_meeting(harness_fixture("race_api.json"))
    assert [r.race_id for r in single.races] == [meta["race_id"]]

    from_meeting = next(r for r in map_meeting(harness_fixture("meeting_api.json")).races
                        if r.race_id == meta["race_id"])
    # captured seconds apart, so odds can differ; everything else is the field itself
    key = lambda r: (r.saddlecloth, r.horse, r.trainer, r.driver, r.driver_claim, r.class_rating, r.handicap, r.form)
    assert [key(r) for r in single.races[0].runners] == [key(r) for r in from_meeting.runners]


def test_real_split_races_round_trips(harness_fixture):
    payload = harness_fixture("meeting_api.json")
    docs = split_races(payload)
    assert len(docs) == len(payload["races"])
    whole = map_meeting(payload)
    for doc, race in zip(docs, whole.races):
        assert len(doc["races"]) == 1
        one = map_meeting(doc)
        assert one.meeting_code == whole.meeting_code
        assert one.races[0].race_id == race.race_id
        assert [r.horse for r in one.races[0].runners] == [r.horse for r in race.runners]
