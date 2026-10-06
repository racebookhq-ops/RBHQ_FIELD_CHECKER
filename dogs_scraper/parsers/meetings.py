"""Parse the day index into meetings, and a meeting page into race URLs."""

from __future__ import annotations

import re

from ..models import Meeting, Race
from ..utils.logging import get_logger
from ..utils.text import clean, distance_m, to_int
from . import selectors as S
from ._common import absolute, try_selectors

log = get_logger("parsers.meetings")

# /racing/<track-slug>/<YYYY-MM-DD>[/<race-no>[/<slug>]]
MEETING_URL_RE = re.compile(r"/racing/(?P<track>[a-z0-9-]+)/(?P<date>\d{4}-\d{2}-\d{2})/?$")
RACE_URL_RE = re.compile(
    r"/racing/(?P<track>[a-z0-9-]+)/(?P<date>\d{4}-\d{2}-\d{2})/(?P<race>\d{1,2})(?:/(?P<slug>[a-z0-9-]+))?"
)

# The index groups meetings under state headings; map heading text to a code.
STATE_KEYWORDS = {
    "new south wales": "NSW", "nsw": "NSW",
    "victoria": "VIC", "vic": "VIC",
    "queensland": "QLD", "qld": "QLD",
    "south australia": "SA", "sa": "SA",
    "western australia": "WA", "wa": "WA",
    "tasmania": "TAS", "tas": "TAS",
    "northern territory": "NT", "nt": "NT",
    "new zealand": "NZ", "nz": "NZ",
}


def _state_from(text: str | None) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for keyword, code in STATE_KEYWORDS.items():
        if keyword in lowered:
            return code
    return None


def parse_meeting_list(page, meeting_date: str, base_url: str) -> list[Meeting]:
    """Extract every meeting on the day index page.

    Works off URL shape rather than CSS classes, so a restyle doesn't break it.
    """
    meetings: dict[str, Meeting] = {}

    for link in page.css("a"):
        href = link.attrib.get("href") if hasattr(link, "attrib") else None
        if not href:
            continue
        match = MEETING_URL_RE.search(href) or RACE_URL_RE.search(href)
        if not match:
            continue
        if match.group("date") != meeting_date:
            continue

        slug = match.group("track")
        if slug in meetings:
            continue

        url = absolute(base_url, f"/racing/{slug}/{meeting_date}")
        label = clean(link.text) if hasattr(link, "text") else None
        meetings[slug] = Meeting(
            track=label if label and not label.isdigit() else _title_from_slug(slug),
            track_slug=slug,
            state=_state_from(label),
            meeting_date=meeting_date,
            url=url,
        )

    log.info("found %d meetings for %s", len(meetings), meeting_date)
    return list(meetings.values())


def _title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-"))


def parse_meeting_page(page, meeting: Meeting, base_url: str) -> Meeting:
    """Fill in a meeting's race stubs (number, name, distance, URL)."""
    title = try_selectors(page, S.MEETING_TITLE)
    if title:
        meeting.track = clean(title.split("|")[0]) or meeting.track
    meeting_condition = try_selectors(page, S.MEETING_TRACK_CONDITION)

    races: dict[int, Race] = {}
    for link in page.css("a"):
        href = link.attrib.get("href") if hasattr(link, "attrib") else None
        if not href:
            continue
        match = RACE_URL_RE.search(href)
        if not match or match.group("date") != meeting.meeting_date:
            continue
        if match.group("track") != meeting.track_slug:
            continue

        number = to_int(match.group("race"))
        if number is None or number in races:
            continue

        text = clean(link.text) if hasattr(link, "text") else None
        slug = match.group("slug")
        races[number] = Race(
            race_number=number,
            name=text if text and len(text) > 3 else (_title_from_slug(slug) if slug else None),
            distance_m=distance_m(text),
            track_condition=meeting_condition,
            url=absolute(base_url, href.split("?")[0]),
        )

    meeting.races = [races[n] for n in sorted(races)]
    meeting.race_count = len(meeting.races)
    log.info("%s: %d races", meeting.track, meeting.race_count)
    return meeting
