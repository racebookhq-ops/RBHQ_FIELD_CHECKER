"""api.harness.org.au JSON -> models.

Mapped from a real capture of `/racing/{meetingCode}/` and
`/racing/{meetingCode}/{raceId}` (6 Oct 2026, Albion Park). Both return the same
wrapper - meeting fields plus a `races` list - and the single-race call simply
has one race in it. Field names that are not in a captured sample are not used.

Mapping decisions worth knowing:

* `odds` is `woo_average_odds`, because that is what the page's Odds column
  shows (checked against the rendered grid). `forecast_odds` is a different
  number and is ignored.
* The handicap is `formatted_handicap` as printed ("Fr1", "Sr1", "10m").
* The driver claim comes from `driver_concession_flags` ("(C)", "(C,5)").
* Start times are converted to Australia/Sydney, whatever the track's zone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dogs_scraper.utils.dates import RACING_TZ

from .config import BASE_URL
from .models import Meeting, Race, Runner

START_TYPES = {"MS": "mobile", "SS": "standing"}


def _num(value: Any) -> int | float | None:
    """Numbers arrive as ints, floats or strings ("2.60"); return int when whole."""
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


def _int(value: Any) -> int | None:
    n = _num(value)
    return int(n) if n is not None else None


def to_sydney_iso(value: str | None) -> str | None:
    """'2026-10-06T13:45:00+11:00' -> Sydney-time ISO with offset."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(RACING_TZ).isoformat()
    except ValueError:
        return None


def map_runner(data: dict[str, Any]) -> Runner:
    stats = data.get("stats_at_race_time") or {}
    return Runner(
        saddlecloth=_int(data.get("saddlecloth_number")),
        horse=(data.get("horse") or {}).get("name"),
        form=stats.get("last_five_starts_form"),
        trainer=(data.get("trainer") or {}).get("display_name"),
        driver=(data.get("driver") or {}).get("display_name"),
        driver_claim=data.get("driver_concession_flags"),
        class_rating=stats.get("horse_class"),
        handicap=data.get("formatted_handicap") or data.get("barrier"),
        odds=_num(data.get("woo_average_odds")),
        scratched=bool(data.get("is_scratching")),
    )


def map_race(data: dict[str, Any], meeting: Meeting | None = None,
             base_url: str = BASE_URL) -> Race:
    record = data.get("track_record") or {}
    start_code = data.get("start_type")
    race = Race(
        race_id=data.get("rise_race_code"),
        race_no=_int(data.get("race_number")),
        start_time=to_sydney_iso(data.get("scheduled_start_time")),
        name=data.get("name"),
        prizemoney=_num(data.get("total_prize_money")),
        class_text=data.get("race_class"),
        conditions=data.get("race_notes"),
        start_type=START_TYPES.get(start_code, start_code),
        distance_m=_int(data.get("distance")),
        track_record_horse=record.get("horse_name"),
        track_record_time=record.get("time_mile_rate"),
        track_record_distance_m=_int(record.get("distance")),
        bet_types=data.get("bet_types"),
        status=data.get("race_status"),
        runners=[map_runner(r) for r in data.get("runners") or []],
        parsed_from="json",
    )
    if meeting is not None and meeting.date and meeting.track_slug and meeting.meeting_code:
        race.url = (f"{base_url}/racing/{meeting.date}/{meeting.track_slug}/"
                    f"{meeting.meeting_code}/meeting/{race.race_id}/{race.race_no}/fields")
    race.runners.sort(key=lambda r: (r.saddlecloth is None, r.saddlecloth or 0))
    return race


def map_meeting(payload: dict[str, Any], base_url: str = BASE_URL) -> Meeting:
    """Map a `/racing/{meetingCode}/...` response, all races it contains."""
    track = payload.get("track") or {}
    slug = (track.get("slug") or "").strip("/") or None
    date = payload.get("date")
    code = payload.get("rise_meeting_code")
    meeting = Meeting(
        date=date,
        track_name=track.get("desktop_display_name"),
        track_slug=slug,
        state=(track.get("state") or "").upper() or None,
        meeting_code=code,
        circumference_m=_num(track.get("circumference")),
        straight_length_m=_num(track.get("home_straight_length")),
        front_line_mobile=_int(track.get("max_front_row_mobile")),
        front_line_standing=_int(track.get("max_row_standing")),
        is_trial=payload.get("is_trial"),
        url=f"{base_url}/racing/{date}/{slug}/{code}/meeting/fields" if (date and slug and code) else None,
    )
    meeting.races = [map_race(r, meeting, base_url) for r in payload.get("races") or []]
    meeting.races.sort(key=lambda r: (r.race_no is None, r.race_no or 0))
    return meeting


def split_races(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One single-race document per race in a meeting response.

    Each has the same shape as the `/racing/{meetingCode}/{raceId}` response
    (meeting fields + a one-item `races` list), which is what gets saved under
    data/raw/ and what map_meeting() reads back.
    """
    header = {k: v for k, v in payload.items() if k != "races"}
    return [{**header, "races": [race]} for race in payload.get("races") or []]
