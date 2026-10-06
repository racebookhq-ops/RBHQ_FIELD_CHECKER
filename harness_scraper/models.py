"""Data model for a day of Australian harness racing.

    DayCard
      └── Meeting (one track, one date)
            └── Race
                  └── Runner (one horse, one saddlecloth)

Same outer shape as dogs_scraper.models.DayCard so the comparison layer can
treat both alike later. Output is flattened to one row per runner (`rows()`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _clean(value: Any) -> Any:
    """Normalise empty-ish values to None so diffs don't trip on '' vs null."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


@dataclass
class Runner:
    saddlecloth: int | None = None
    horse: str | None = None
    form: str | None = None                # last five starts, e.g. "37418"
    trainer: str | None = None
    driver: str | None = None
    driver_claim: str | None = None        # "(C)", "(C,5)" - kept apart from the name
    class_rating: str | None = None        # as printed, e.g. "NR47", "NR104 B4"
    handicap: str | None = None            # "Fr1", "Sr1", "10m" ... as the API prints it
    odds: float | None = None              # the figure in the site's Odds column
    scratched: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {k: _clean(v) for k, v in self.__dict__.items()}


@dataclass
class Race:
    race_id: str | None = None             # e.g. PCC06102607 - NOT in race order
    race_no: int | None = None
    start_time: str | None = None          # ISO 8601 with offset, Australia/Sydney
    name: str | None = None
    prizemoney: float | None = None
    class_text: str | None = None          # eligibility, e.g. "NR up to 55. RBD. Trotters"
    conditions: str | None = None          # race notes
    start_type: str | None = None          # "mobile" | "standing"
    distance_m: int | None = None
    track_record_horse: str | None = None
    track_record_time: str | None = None
    track_record_distance_m: int | None = None
    bet_types: str | None = None
    status: str | None = None
    url: str | None = None
    runners: list[Runner] = field(default_factory=list)
    #: How this race was obtained: "json" or "text" (fallback)
    parsed_from: str = "json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "race_id": self.race_id,
            "race_no": self.race_no,
            "start_time": self.start_time,
            "name": _clean(self.name),
            "prizemoney": self.prizemoney,
            "class_text": _clean(self.class_text),
            "conditions": _clean(self.conditions),
            "start_type": self.start_type,
            "distance_m": self.distance_m,
            "track_record": {
                "horse": self.track_record_horse,
                "time": self.track_record_time,
                "distance_m": self.track_record_distance_m,
            },
            "bet_types": _clean(self.bet_types),
            "status": self.status,
            "url": self.url,
            "parsed_from": self.parsed_from,
            "runners": [r.to_dict() for r in self.runners],
        }


@dataclass
class Meeting:
    date: str | None = None                # YYYY-MM-DD
    track_name: str | None = None
    track_slug: str | None = None
    state: str | None = None               # NSW / VIC / QLD / SA / WA / TAS / NT
    meeting_code: str | None = None        # track code + DDMMYY, e.g. PC061026
    circumference_m: float | None = None
    straight_length_m: float | None = None
    front_line_mobile: int | None = None
    front_line_standing: int | None = None
    is_trial: bool | None = None
    url: str | None = None
    races: list[Race] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "track_name": self.track_name,
            "track_slug": self.track_slug,
            "state": self.state,
            "meeting_code": self.meeting_code,
            "is_trial": self.is_trial,
            "url": self.url,
            "track_layout": {
                "circumference_m": self.circumference_m,
                "straight_length_m": self.straight_length_m,
                "front_line_mobile": self.front_line_mobile,
                "front_line_standing": self.front_line_standing,
            },
            "races": [r.to_dict() for r in self.races],
        }


#: Column order for CSV and the JSON rows. Meeting, then race, then runner.
COLUMNS = [
    "date", "track_name", "track_slug", "state", "meeting_code",
    "circumference_m", "straight_length_m", "front_line_mobile", "front_line_standing", "is_trial",
    "race_id", "race_no", "start_time", "race_name", "prizemoney", "class_text", "conditions",
    "start_type", "distance_m", "track_record_horse", "track_record_time",
    "track_record_distance_m", "bet_types",
    "saddlecloth", "horse", "form", "trainer", "driver", "driver_claim",
    "class_rating", "handicap", "odds", "scratched",
]


@dataclass
class DayCard:
    meeting_date: str
    scraped_at: str
    source: str = "harness.org.au"
    meetings: list[Meeting] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_races(self) -> int:
        return sum(len(m.races) for m in self.meetings)

    @property
    def total_runners(self) -> int:
        return sum(len(r.runners) for m in self.meetings for r in m.races)

    def rows(self) -> list[dict[str, Any]]:
        out = []
        for m in self.meetings:
            for r in m.races:
                for u in r.runners:
                    out.append({
                        "date": m.date, "track_name": m.track_name, "track_slug": m.track_slug,
                        "state": m.state, "meeting_code": m.meeting_code,
                        "circumference_m": m.circumference_m,
                        "straight_length_m": m.straight_length_m,
                        "front_line_mobile": m.front_line_mobile,
                        "front_line_standing": m.front_line_standing,
                        "is_trial": m.is_trial,
                        "race_id": r.race_id, "race_no": r.race_no, "start_time": r.start_time,
                        "race_name": _clean(r.name), "prizemoney": r.prizemoney,
                        "class_text": _clean(r.class_text), "conditions": _clean(r.conditions),
                        "start_type": r.start_type, "distance_m": r.distance_m,
                        "track_record_horse": r.track_record_horse,
                        "track_record_time": r.track_record_time,
                        "track_record_distance_m": r.track_record_distance_m,
                        "bet_types": _clean(r.bet_types),
                        **u.to_dict(),
                    })
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "meeting_date": self.meeting_date,
            "scraped_at": self.scraped_at,
            "source": self.source,
            "summary": {
                "meetings": len(self.meetings),
                "races": self.total_races,
                "runners": self.total_runners,
                "errors": len(self.errors),
            },
            "errors": self.errors,
            "meetings": [m.to_dict() for m in self.meetings],
        }


def card_from_dict(data: dict[str, Any]) -> DayCard:
    """Rebuild a DayCard from a fields.json (or rbhq_fields.json) written by this package.

    Reads the nested format (meetings -> races -> runners). Files from before
    the nesting change hold flat runner rows under "runners" and are still
    accepted. Lets the comparison replay saved output for free.
    """
    if "meetings" in data:
        return _card_from_nested(data)
    return _card_from_rows(data)


def _card_from_nested(data: dict[str, Any]) -> DayCard:
    card = DayCard(
        meeting_date=data.get("meeting_date", ""),
        scraped_at=data.get("scraped_at", ""),
        source=data.get("source", "unknown"),
        errors=data.get("errors", []) or [],
    )
    for m in data.get("meetings") or []:
        layout = m.get("track_layout") or {}
        meeting = Meeting(
            date=m.get("date"), track_name=m.get("track_name"), track_slug=m.get("track_slug"),
            state=m.get("state"), meeting_code=m.get("meeting_code"), is_trial=m.get("is_trial"),
            url=m.get("url"), circumference_m=layout.get("circumference_m"),
            straight_length_m=layout.get("straight_length_m"),
            front_line_mobile=layout.get("front_line_mobile"),
            front_line_standing=layout.get("front_line_standing"))
        for r in m.get("races") or []:
            record = r.get("track_record") or {}
            race = Race(
                race_id=r.get("race_id"), race_no=r.get("race_no"), start_time=r.get("start_time"),
                name=r.get("name"), prizemoney=r.get("prizemoney"), class_text=r.get("class_text"),
                conditions=r.get("conditions"), start_type=r.get("start_type"),
                distance_m=r.get("distance_m"), track_record_horse=record.get("horse"),
                track_record_time=record.get("time"), track_record_distance_m=record.get("distance_m"),
                bet_types=r.get("bet_types"), status=r.get("status"), url=r.get("url"),
                parsed_from=r.get("parsed_from") or "json")
            race.runners = [Runner(**{k: u.get(k) for k in Runner.__dataclass_fields__ if k in u})
                            for u in r.get("runners") or []]
            meeting.races.append(race)
        card.meetings.append(meeting)
    return card


def _card_from_rows(data: dict[str, Any]) -> DayCard:
    """The pre-nesting format: one flat row per runner, regrouped from repeated columns."""
    card = DayCard(
        meeting_date=data.get("meeting_date", ""),
        scraped_at=data.get("scraped_at", ""),
        source=data.get("source", "unknown"),
        errors=data.get("errors", []) or [],
    )
    meetings: dict[tuple, Meeting] = {}
    races: dict[tuple, Race] = {}
    for row in data.get("runners") or []:
        mkey = (row.get("date"), row.get("meeting_code") or row.get("track_slug"))
        meeting = meetings.get(mkey)
        if meeting is None:
            meeting = meetings[mkey] = Meeting(
                date=row.get("date"), track_name=row.get("track_name"),
                track_slug=row.get("track_slug"), state=row.get("state"),
                meeting_code=row.get("meeting_code"),
                circumference_m=row.get("circumference_m"),
                straight_length_m=row.get("straight_length_m"),
                front_line_mobile=row.get("front_line_mobile"),
                front_line_standing=row.get("front_line_standing"),
                is_trial=row.get("is_trial"))
            card.meetings.append(meeting)
        rkey = mkey + (row.get("race_id") or row.get("race_no"),)
        race = races.get(rkey)
        if race is None:
            race = races[rkey] = Race(
                race_id=row.get("race_id"), race_no=row.get("race_no"),
                start_time=row.get("start_time"), name=row.get("race_name"),
                prizemoney=row.get("prizemoney"), class_text=row.get("class_text"),
                conditions=row.get("conditions"), start_type=row.get("start_type"),
                distance_m=row.get("distance_m"),
                track_record_horse=row.get("track_record_horse"),
                track_record_time=row.get("track_record_time"),
                track_record_distance_m=row.get("track_record_distance_m"),
                bet_types=row.get("bet_types"))
            meeting.races.append(race)
        race.runners.append(Runner(
            saddlecloth=row.get("saddlecloth"), horse=row.get("horse"), form=row.get("form"),
            trainer=row.get("trainer"), driver=row.get("driver"),
            driver_claim=row.get("driver_claim"), class_rating=row.get("class_rating"),
            handicap=row.get("handicap"), odds=row.get("odds"),
            scratched=bool(row.get("scratched"))))
    return card
