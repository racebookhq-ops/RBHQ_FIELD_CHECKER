"""Index-page discovery: link parsing, the page's JSON listing, and merging them.

The pure-regex tests need no fixture. The rest run against the real capture in
tests/fixtures/harness/ (refresh with tools/dump_harness.py).
"""

import re

from harness_scraper.discovery import (DiscoveredMeeting, merge_discovery,
                                       parse_index_json, parse_index_links)

BASE = "https://www.harness.org.au"
RACE = "/racing/2026-10-06/tabcorp-pk-menangle/PC061026/meeting/PCC06102607/1/fields"
RACE2 = "/racing/2026-10-06/tabcorp-pk-menangle/PC061026/meeting/PCC06102609/2/fields"
MEETING = "/racing/2026-10-06/tabcorp-pk-menangle/PC061026/meeting/fields"


def html(*hrefs):
    return "".join(f'<a href="{h}">x</a>' for h in hrefs)


# -- link patterns (from the brief) --------------------------------------------
def test_race_link_is_parsed_into_its_parts():
    [m] = parse_index_links(html(RACE), "2026-10-06")
    assert (m.date, m.track_slug, m.meeting_code) == ("2026-10-06", "tabcorp-pk-menangle", "PC061026")
    assert [(r.race_id, r.race_no) for r in m.races] == [("PCC06102607", 1)]
    assert m.url == BASE + MEETING


def test_race_ids_are_taken_from_links_not_computed():
    # R1 = ...07, R2 = ...09: ids are not sequential, and race order follows race_no
    [m] = parse_index_links(html(RACE2, RACE, MEETING), "2026-10-06")
    assert [(r.race_no, r.race_id) for r in m.races] == [(1, "PCC06102607"), (2, "PCC06102609")]


def test_absolute_urls_queries_and_duplicates_are_handled():
    links = html(BASE + RACE + "?x=1", RACE, RACE)
    [m] = parse_index_links(links, "2026-10-06")
    assert len(m.races) == 1


def test_other_dates_and_unrelated_links_are_ignored():
    other = RACE.replace("2026-10-06", "2026-10-07")
    links = html(other, "/racing/fields", "/racing/2026-10-06/tabcorp-pk-menangle/PC061026/meeting/PCC06102607/1/form",
                 "/about", "/racing/stewards-reports/PC061026")
    assert parse_index_links(links, "2026-10-06") == []
    assert len(parse_index_links(links)) == 1            # no day filter -> the other-date race is kept


# -- the page's JSON -----------------------------------------------------------
def listing(**over):
    meeting = {
        "rise_meeting_code": "MX061026", "is_trial": True,
        "track": {"slug": "/melton", "desktop_display_name": "Melton", "state": "vic"},
        "races": [{"rise_race_code": "MXQ06102610", "race_number": 1}],
    }
    meeting.update(over)
    return {"date": "2026-10-06", "meetings": [meeting]}


def test_index_json_gives_state_trial_flag_and_a_url():
    [m] = parse_index_json(listing())
    assert (m.state, m.is_trial, m.track_slug, m.track_name) == ("VIC", True, "melton", "Melton")
    assert m.url == f"{BASE}/racing/2026-10-06/melton/MX061026/meeting/fields"
    assert [(r.race_id, r.race_no) for r in m.races] == [("MXQ06102610", 1)]


def test_index_json_tolerates_garbage():
    assert parse_index_json(None) == []
    assert parse_index_json({"date": "2026-10-06", "meetings": [{"track": {}}]}) == []


def test_trials_are_dropped_unless_asked_for():
    trial = parse_index_json(listing())
    assert merge_discovery([], trial) == []
    assert [m.meeting_code for m in merge_discovery([], trial, include_trials=True)] == ["MX061026"]


def test_trial_flag_from_json_overrides_a_leaked_link():
    # the "next to go" widget can link a trial race even though the day view hides trials
    leaked = parse_index_links(html("/racing/2026-10-06/melton/MX061026/meeting/MXQ06102610/1/fields"), "2026-10-06")
    assert merge_discovery(leaked, parse_index_json(listing())) == []


def test_state_filter():
    j = parse_index_json(listing(is_trial=False))
    assert merge_discovery([], j, states=["NSW"]) == []
    assert len(merge_discovery([], j, states=["vic"])) == 1


def test_unknown_trial_status_is_kept_until_the_meeting_json_says_otherwise():
    links = parse_index_links(html(MEETING), "2026-10-06")
    assert links[0].is_trial is None
    assert len(merge_discovery(links, [])) == 1


# -- against the real capture --------------------------------------------------
def test_real_index_yields_meetings(harness_fixture):
    meta = harness_fixture("fixture_meta.json")
    links = parse_index_links(harness_fixture("index.html"), meta["date"], BASE)
    assert links, "no meetings parsed from the index page"
    for m in links:
        assert re.fullmatch(r"[A-Z]{2}\d{6}[A-Z]?", m.meeting_code), m.meeting_code
        assert m.url.startswith(BASE)
        assert all(r.race_id and r.race_no for r in m.races)


def test_real_index_links_agree_with_the_pages_json(harness_fixture):
    meta = harness_fixture("fixture_meta.json")
    links = {m.meeting_code: m for m in parse_index_links(harness_fixture("index.html"), meta["date"], BASE)}
    listed = {m.meeting_code: m for m in parse_index_json(harness_fixture("index_api.json"), BASE)}

    assert set(links) <= set(listed), "a linked meeting is missing from the JSON listing"
    # trials are hidden on the page, so everything linked is a non-trial
    assert not any(listed[c].is_trial for c in links)
    for code, m in links.items():
        if m.races and listed[code].races:
            assert {r.race_id for r in m.races} == {r.race_id for r in listed[code].races}, code


def test_real_merge_finds_the_captured_meeting(harness_fixture):
    meta = harness_fixture("fixture_meta.json")
    merged = merge_discovery(
        parse_index_links(harness_fixture("index.html"), meta["date"], BASE),
        parse_index_json(harness_fixture("index_api.json"), BASE),
    )
    by_code = {m.meeting_code: m for m in merged}
    assert meta["meeting_code"] in by_code
    m = by_code[meta["meeting_code"]]
    assert m.state and m.is_trial is False
    assert any(r.race_id == meta["race_id"] and r.race_no == meta["race_no"] for r in m.races)
