"""Finding the day's meetings and race ids from the fields index page.

Two views of the same page are combined:

* the `<a href>` links in the rendered HTML (server-rendered, so they are
  always there) - the primary source of meeting codes and race ids;
* the JSON the page itself requests (`/racing/fields?date=`), which adds the
  state and is_trial flag per meeting and also lists trial meetings, which the
  default page hides.

Race ids are NEVER computed. They are not in race order (R1 = PCC06102607,
R2 = PCC06102609) so they are only ever taken from links or from the API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .config import BASE_URL

_DATE = r"(\d{4}-\d{2}-\d{2})"
#: /racing/{date}/{track-slug}/{meetingCode}/meeting/fields
MEETING_LINK_RE = re.compile(rf"^/racing/{_DATE}/([^/]+)/([A-Za-z0-9]+)/meeting/fields/?$")
#: /racing/{date}/{track-slug}/{meetingCode}/meeting/{raceId}/{raceNo}/fields
RACE_LINK_RE = re.compile(
    rf"^/racing/{_DATE}/([^/]+)/([A-Za-z0-9]+)/meeting/([A-Za-z0-9]+)/(\d+)/fields/?$"
)
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)


@dataclass
class IndexRace:
    race_id: str
    race_no: int


@dataclass
class DiscoveredMeeting:
    date: str
    track_slug: str
    meeting_code: str
    url: str
    races: list[IndexRace] = field(default_factory=list)
    track_name: str | None = None
    state: str | None = None
    is_trial: bool | None = None       # None = unknown until the meeting JSON arrives


def _path_of(href: str) -> str:
    """Strip scheme/host, query and fragment so only the path is matched."""
    href = re.sub(r"^https?://[^/]+", "", href.strip())
    return re.split(r"[?#]", href, maxsplit=1)[0]


def parse_index_links(html: str, day: str | None = None,
                      base_url: str = BASE_URL) -> list[DiscoveredMeeting]:
    """Every meeting and race link in the index HTML, grouped by meeting.

    `day` (YYYY-MM-DD) drops links for other dates - the page also carries a
    "next to go" widget that always links to today's races.
    """
    meetings: dict[str, DiscoveredMeeting] = {}

    def get(date: str, slug: str, code: str) -> DiscoveredMeeting:
        if code not in meetings:
            meetings[code] = DiscoveredMeeting(
                date=date, track_slug=slug, meeting_code=code,
                url=f"{base_url}/racing/{date}/{slug}/{code}/meeting/fields",
            )
        return meetings[code]

    for href in _HREF_RE.findall(html):
        path = _path_of(href)
        if m := MEETING_LINK_RE.match(path):
            date, slug, code = m.groups()
            if day is None or date == day:
                get(date, slug, code)
        elif m := RACE_LINK_RE.match(path):
            date, slug, code, race_id, race_no = m.groups()
            if day is None or date == day:
                meeting = get(date, slug, code)
                if all(r.race_id != race_id for r in meeting.races):
                    meeting.races.append(IndexRace(race_id=race_id, race_no=int(race_no)))

    out = list(meetings.values())
    for meeting in out:
        meeting.races.sort(key=lambda r: r.race_no)
    return out


def parse_index_json(payload: dict[str, Any] | None, base_url: str = BASE_URL) -> list[DiscoveredMeeting]:
    """Meetings from the captured `/racing/fields?date=` response."""
    out: list[DiscoveredMeeting] = []
    if not isinstance(payload, dict):
        return out
    date = payload.get("date")
    for m in payload.get("meetings") or []:
        code = m.get("rise_meeting_code")
        track = m.get("track") or {}
        slug = (track.get("slug") or "").strip("/")
        if not (code and slug and date):
            continue
        races = sorted(
            (IndexRace(race_id=r["rise_race_code"], race_no=int(r["race_number"]))
             for r in m.get("races") or []
             if r.get("rise_race_code") and r.get("race_number") is not None),
            key=lambda r: r.race_no,
        )
        out.append(DiscoveredMeeting(
            date=date, track_slug=slug, meeting_code=code,
            url=f"{base_url}/racing/{date}/{slug}/{code}/meeting/fields",
            races=races,
            track_name=track.get("desktop_display_name"),
            state=(track.get("state") or "").upper() or None,
            is_trial=m.get("is_trial"),
        ))
    return out


def merge_discovery(from_links: list[DiscoveredMeeting], from_json: list[DiscoveredMeeting],
                    *, include_trials: bool = False,
                    states: list[str] | None = None) -> list[DiscoveredMeeting]:
    """Combine both views, then apply the trial and state filters.

    Links win for the URL and race ids; JSON fills in state / is_trial / name
    and supplies meetings (such as trials) that have no link.
    """
    merged: dict[str, DiscoveredMeeting] = {m.meeting_code: m for m in from_links}
    for j in from_json:
        m = merged.get(j.meeting_code)
        if m is None:
            merged[j.meeting_code] = j
            continue
        m.track_name = m.track_name or j.track_name
        m.state = m.state or j.state
        if m.is_trial is None:
            m.is_trial = j.is_trial
        if not m.races:
            m.races = j.races

    wanted = {s.upper() for s in (states or [])}
    out = []
    for m in merged.values():
        if m.is_trial and not include_trials:
            continue
        if wanted and m.state and m.state not in wanted:
            continue
        out.append(m)
    return out
