"""Turn the RBHQ feed's JSON into the same DayCard the dogs scraper produces.

The two sources describe the same races in different shapes, so everything
awkward about the translation lives here.

    feed                          DayCard
    ----                          -------
    meetings[]                    Meeting
    meetings[].events[]           Race
    meetings[].events[].Runners[] Runner

Four things are not a straight field copy:

* **The box is `barrier`, not `runnerNumber`.** `runnerNumber` is the entry
  number on the card, which keeps counting past the field into the reserves;
  `barrier` is the rug the dog actually runs out of. A reserve that has not
  been given a box carries `barrier: 0`, and comes through with `box=None`
  rather than being left out - it is still a greyhound that may be running.

* **An empty box is a runner named `"...."`** with no trainer, exactly the
  way thedogs.com.au renders "Vacant Box". Those become a Runner with the box
  set, `name=None` and `scratched=True`, so an empty box 3 is visible rather
  than a hole in the numbering - same as the dogs scraper.

* **Two entries can share a barrier.** When a dog is scratched a reserve is
  promoted into its box, and the feed keeps both rows. Both are reported -
  the live one and the one that came out - because the comparison matches on
  who is running, not on what is in each box.

* **Times are UTC.** thedogs publishes every start in Australia/Sydney local
  time regardless of the track's own state, so we convert to the same zone and
  the two cards line up without any timezone reasoning by the consumer.
"""

from __future__ import annotations

import re
from datetime import date as _date, datetime, timezone
from typing import Any, Iterable

from dogs_scraper.models import DayCard, Meeting, Race, Runner
from dogs_scraper.utils.dates import RACING_TZ, now_local
from dogs_scraper.utils.text import clean, slugify, to_int

from .logging import get_logger

log = get_logger("mapper")

SOURCE_NAME = "rbhq-api"

#: The feed carries thoroughbreds and harness too; "G" is greyhounds.
GREYHOUND_TYPE = "G"

#: Default to Australian meetings - the dogs scraper only covers those, so
#: anything else has nothing to be compared against.
DEFAULT_COUNTRIES = ("AU",)

#: A box with no dog in it comes through as a name of bare dots.
_VACANT_RE = re.compile(r"^\.+$")


def is_vacant(name: str | None) -> bool:
    """True when the feed is describing an empty box rather than a greyhound."""
    return bool(_VACANT_RE.match((name or "").strip()))


def utc_to_local(value: str | None) -> str | None:
    """'2026-09-22T01:10:00.000Z' -> '2026-09-22T11:10:00+10:00'."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(RACING_TZ).isoformat()


def meeting_day(value: str | None) -> str | None:
    """The racing day, as YYYY-MM-DD.

    `meetingDate` is midnight UTC standing in for a calendar day, so the date
    part is taken as-is rather than converted - converting would roll an
    Australian meeting back to the previous day.
    """
    if not value:
        return None
    text = str(value).strip()
    return text.split("T")[0] or None


def track_name(venue: str | None) -> str | None:
    """'ANGLE PARK' -> 'Angle Park'. The feed shouts; thedogs does not."""
    c = clean(venue)
    return c.title() if c else None


# --------------------------------------------------------------------------
# runners
# --------------------------------------------------------------------------
def _build_runner(box: int | None, entry: dict[str, Any]) -> Runner:
    name = clean(entry.get("name"))
    vacant = is_vacant(entry.get("name"))

    runner = Runner(
        box=box,
        name=None if vacant else name,
        trainer=clean(entry.get("trainer")),
        scratched=bool(entry.get("scratched")) or vacant,
        scratch_time=utc_to_local(entry.get("scratchingTimestamp")),
    )
    # weight, form, best time and odds are not published in this feed. They stay
    # None rather than being invented, so a comparison skips them instead of
    # reporting a phantom difference.

    runner.raw["runner_number"] = to_int(entry.get("runnerNumber"))
    if box is None:
        runner.raw["reserve"] = True
    if vacant:
        runner.raw["vacant"] = True
    if entry.get("emergency"):
        runner.raw["emergency"] = True
    if entry.get("finishPosition") is not None:
        runner.raw["finish_position"] = to_int(entry.get("finishPosition"))
    if entry.get("scratchType"):
        runner.raw["scratch_type"] = entry.get("scratchType")
    # Always {} in every sample seen, so the shape is unknown - carried through
    # verbatim rather than guessed at.
    if entry.get("prices"):
        runner.raw["prices"] = entry["prices"]
    return runner


def build_runners(raw_runners: Iterable[dict[str, Any]]) -> list[Runner]:
    """One Runner per entry the feed lists - every entry, without exception.

    Two shapes used to be dropped here, and both were mistakes:

    * An entry on `barrier: 0` is a reserve that has not been given a box. It
      is still a greyhound that may be running, and the feed numbers it 9 or
      10. Filing it away as "not a box" hid it from the comparison, which then
      reported it as a dog in the field we did not have at all.
    * Two entries can share a barrier when a reserve is promoted into a
      scratching. Collapsing them to one lost the dog that came out.

    Boxes are not what the comparison matches on, so neither case needs
    resolving here - reporting the feed faithfully is enough. A reserve keeps
    `box=None` and is flagged `raw.reserve`.
    """
    runners = [
        _build_runner(to_int(entry.get("barrier")) or None, entry)
        for entry in raw_runners or []
    ]
    # Box order, with the unboxed reserves last, so the card reads the way the
    # race does.
    runners.sort(key=lambda r: (r.box is None, r.box or 0,
                                r.raw.get("runner_number") or 0))
    return runners


# --------------------------------------------------------------------------
# races and meetings
# --------------------------------------------------------------------------
def build_race(event: dict[str, Any]) -> Race:
    runners = build_runners(event.get("Runners"))

    race = Race(
        race_number=to_int(event.get("eventNumber")),
        name=clean(event.get("eventName")),
        distance_m=to_int(event.get("distance")),
        grade=clean(event.get("class")),
        start_time_local=utc_to_local(event.get("startTime")),
        runners=runners,
    )
    # No public race page is published for this feed, so `url` stays None
    # rather than pointing at a link that does not resolve.

    race.raw["event_id"] = event.get("eventId")
    if event.get("status"):
        race.raw["status"] = event["status"]
    if event.get("closeTime"):
        race.raw["close_time"] = utc_to_local(event["closeTime"])
    if clean(event.get("weather")):
        race.raw["weather"] = clean(event["weather"])
    return race


def build_meeting(raw_meeting: dict[str, Any], events: list[dict[str, Any]]) -> Meeting:
    venue = raw_meeting.get("venue")
    meeting = Meeting(
        track=track_name(venue),
        track_slug=slugify(venue),
        state=clean(raw_meeting.get("state")),
        meeting_date=meeting_day(raw_meeting.get("meetingDate")),
    )
    meeting.races = sorted(
        (build_race(e) for e in events),
        key=lambda r: (r.race_number is None, r.race_number or 0),
    )

    meeting.raw["meeting_id"] = raw_meeting.get("meetingId")
    if raw_meeting.get("country"):
        meeting.raw["country"] = raw_meeting["country"]

    published = to_int((events[0] if events else {}).get("numberOfEvents"))
    if published and published != len(meeting.races):
        # The feed sometimes omits races that have already been settled.
        meeting.raw["events_published"] = published

    alternates = sorted({
        clean(n) for e in events for n in (e.get("AlternateVenueNames") or []) if clean(n)
    })
    if alternates:
        # The other side of a comparison may use any of these spellings.
        meeting.raw["alternate_names"] = alternates
    return meeting


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def build_card(payload: dict[str, Any], day: _date | None = None, *,
               countries: Iterable[str] = DEFAULT_COUNTRIES,
               states: Iterable[str] = (),
               tracks: Iterable[str] = ()) -> DayCard:
    """Map a feed response onto a DayCard.

    `day` filters to one racing day; pass None to keep everything the payload
    happens to contain.
    """
    wanted_countries = {c.upper() for c in countries if c}
    wanted_states = {s.upper() for s in states if s}
    wanted_tracks = {t.lower() for t in tracks if t}
    wanted_day = day.isoformat() if day else None

    card = DayCard(
        meeting_date=wanted_day or "",
        scraped_at=now_local().isoformat(),
        source=SOURCE_NAME,
    )

    if not payload.get("successful", True):
        card.errors.append({"stage": "feed", "error": clean(payload.get("message"))
                            or "feed reported successful=false"})

    skipped_code = skipped_country = skipped_day = 0

    for raw_meeting in payload.get("meetings") or []:
        if clean(raw_meeting.get("type")) != GREYHOUND_TYPE:
            skipped_code += 1
            continue
        if wanted_countries and str(raw_meeting.get("country", "")).upper() not in wanted_countries:
            skipped_country += 1
            continue

        day_str = meeting_day(raw_meeting.get("meetingDate"))
        if wanted_day and day_str != wanted_day:
            skipped_day += 1
            continue

        state = (clean(raw_meeting.get("state")) or "").upper()
        if wanted_states and state not in wanted_states:
            continue

        slug = slugify(raw_meeting.get("venue")) or ""
        if wanted_tracks and slug not in wanted_tracks:
            continue

        events = raw_meeting.get("events") or []
        if not events:
            card.errors.append({
                "stage": "meeting", "track": track_name(raw_meeting.get("venue")),
                "error": "meeting has no events",
            })
            continue

        card.meetings.append(build_meeting(raw_meeting, events))

    card.meetings.sort(key=lambda m: (m.track or "").lower())

    if not card.meeting_date and card.meetings:
        # Unfiltered, the payload can span more than one racing day. Label the
        # card with the earliest so the output filename is decided by content
        # rather than by which track happens to sort first, and say so - every
        # Meeting still carries its own date.
        days = sorted({m.meeting_date for m in card.meetings if m.meeting_date})
        card.meeting_date = days[0] if days else ""
        if len(days) > 1:
            log.warning("payload spans %d racing days (%s); writing them to one "
                        "card labelled %s - pass a date to split them",
                        len(days), ", ".join(days), card.meeting_date)

    log.info("RBHQ: %d meetings, %d races, %d runners "
             "(skipped %d non-greyhound, %d offshore, %d other days)",
             len(card.meetings), card.total_races, card.total_runners,
             skipped_code, skipped_country, skipped_day)
    return card
