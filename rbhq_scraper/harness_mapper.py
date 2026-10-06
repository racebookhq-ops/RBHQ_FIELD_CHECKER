"""Turn the RBHQ feed's harness ("H") meetings into a harness_scraper DayCard.

UNVERIFIED AGAINST A REAL HARNESS RESPONSE. When this was written the feed
returned no harness meetings (and then HTTP 401), so there was no capture to map
from. The feed uses one envelope for every race type - meetings[] -> events[] ->
Runners[] - and this reads only the keys seen on real greyhound responses
(tests/fixtures/rbhq_response.json). Which of those keys harness actually fills,
and what they mean for harness, are assumptions:

* saddlecloth <- `runnerNumber`
* driver      <- `jockey` (the key exists on greyhound runners, always empty)
* `barrier`   is NOT used: harness has no box, and it is unclear whether it
  carries the gate/handicap position, so `handicap` stays None.
* form, class rating, odds, claims and the track details are not in the feed.

Capture one with:  python -m rbhq_scraper --harness --save-response raw_h.json
then check this module (and tests/test_rbhq_harness.py) against it.

Times are UTC in the feed; they are converted to Australia/Sydney to match
harness_scraper's output.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any, Iterable

from dogs_scraper.utils.dates import now_local
from dogs_scraper.utils.text import clean, slugify, to_int
from harness_scraper.models import DayCard, Meeting, Race, Runner

from .logging import get_logger
from .mapper import DEFAULT_COUNTRIES, meeting_day, track_name, utc_to_local

log = get_logger("harness_mapper")

SOURCE_NAME = "rbhq-api"
HARNESS_TYPE = "H"


def build_runner(entry: dict[str, Any]) -> Runner:
    return Runner(
        saddlecloth=to_int(entry.get("runnerNumber")),
        horse=clean(entry.get("name")),
        trainer=clean(entry.get("trainer")),
        driver=clean(entry.get("jockey")),
        scratched=bool(entry.get("scratched")),
    )


def build_race(event: dict[str, Any]) -> Race:
    runners = [build_runner(r) for r in event.get("Runners") or []]
    runners.sort(key=lambda r: (r.saddlecloth is None, r.saddlecloth or 0))
    return Race(
        race_id=str(event["eventId"]) if event.get("eventId") is not None else None,
        race_no=to_int(event.get("eventNumber")),
        start_time=utc_to_local(event.get("startTime")),
        name=clean(event.get("eventName")),
        class_text=clean(event.get("class")),
        distance_m=to_int(event.get("distance")),
        bet_types=", ".join(str(b) for b in event.get("betTypes") or []) or None,
        status=clean(event.get("status")),
        runners=runners,
    )


def build_meeting(raw: dict[str, Any], events: list[dict[str, Any]]) -> Meeting:
    meeting = Meeting(
        date=meeting_day(raw.get("meetingDate")),
        track_name=track_name(raw.get("venue")),
        track_slug=slugify(raw.get("venue")),
        state=(clean(raw.get("state")) or "").upper() or None,
    )
    meeting.races = sorted((build_race(e) for e in events),
                           key=lambda r: (r.race_no is None, r.race_no or 0))
    return meeting


def build_harness_card(payload: dict[str, Any], day: _date | None = None, *,
                       countries: Iterable[str] = DEFAULT_COUNTRIES,
                       states: Iterable[str] = (),
                       tracks: Iterable[str] = ()) -> DayCard:
    """Map a feed response onto a harness DayCard (meetings of type "H" only)."""
    wanted_countries = {c.upper() for c in countries if c}
    wanted_states = {s.upper() for s in states if s}
    wanted_tracks = {t.lower() for t in tracks if t}
    wanted_day = day.isoformat() if day else None

    card = DayCard(meeting_date=wanted_day or "", scraped_at=now_local().isoformat(),
                   source=SOURCE_NAME)
    if not payload.get("successful", True):
        card.errors.append({"stage": "feed", "error": clean(payload.get("message"))
                            or "feed reported successful=false"})

    skipped = 0
    for raw in payload.get("meetings") or []:
        if clean(raw.get("type")) != HARNESS_TYPE:
            skipped += 1
            continue
        if wanted_countries and str(raw.get("country", "")).upper() not in wanted_countries:
            continue
        if wanted_day and meeting_day(raw.get("meetingDate")) != wanted_day:
            continue
        if wanted_states and (clean(raw.get("state")) or "").upper() not in wanted_states:
            continue
        if wanted_tracks and (slugify(raw.get("venue")) or "") not in wanted_tracks:
            continue
        events = raw.get("events") or []
        if not events:
            card.errors.append({"stage": "meeting", "track": track_name(raw.get("venue")),
                                "error": "meeting has no events"})
            continue
        card.meetings.append(build_meeting(raw, events))

    card.meetings.sort(key=lambda m: (m.track_name or "").lower())
    if not card.meeting_date and card.meetings:
        card.meeting_date = min(m.date for m in card.meetings if m.date)

    log.info("RBHQ harness: %d meetings, %d races, %d runners (skipped %d non-harness)",
             len(card.meetings), card.total_races, card.total_runners, skipped)
    return card
