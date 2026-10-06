"""Data model for a day's greyhound racing card.

The shape is deliberately flat and boring so that an LLM agent can diff it
against our own fields without needing to understand the site.

    DayCard
      └── Meeting (one track, one date)
            └── Race (one event)
                  └── Runner (one greyhound in a box)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date as _date
from typing import Any


def _clean(value: Any) -> Any:
    """Normalise empty-ish values to None so diffs don't trip on '' vs null."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


@dataclass
class Runner:
    """A single greyhound entered in a race."""

    box: int | None = None                 # rug / box number, 1-8 (source of truth for matching)
    name: str | None = None                # dog name, as printed
    trainer: str | None = None
    weight_kg: float | None = None
    form: str | None = None                # recent starts string, e.g. "1x24"
    best_time: str | None = None
    prize_money: str | None = None
    odds: float | None = None              # site-displayed fixed odds, if present
    scratched: bool = False
    scratch_time: str | None = None
    dog_url: str | None = None             # link to the dog's profile page
    raw: dict[str, Any] = field(default_factory=dict)   # anything else we scraped

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: _clean(v) for k, v in d.items()}


@dataclass
class Race:
    """One race on a meeting card."""

    race_number: int | None = None
    name: str | None = None
    distance_m: int | None = None
    grade: str | None = None
    start_time_local: str | None = None    # ISO 8601 with offset, Australia/Sydney basis
    prize_money: str | None = None
    track_condition: str | None = None
    comment: str | None = None
    url: str | None = None
    runners: list[Runner] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)   # source-specific ids/state

    @property
    def field_size(self) -> int:
        return len([r for r in self.runners if not r.scratched])

    @property
    def scratchings(self) -> list[int]:
        return sorted(r.box for r in self.runners if r.scratched and r.box)

    def to_dict(self) -> dict[str, Any]:
        return {
            "race_number": self.race_number,
            "name": _clean(self.name),
            "distance_m": self.distance_m,
            "grade": _clean(self.grade),
            "start_time_local": self.start_time_local,
            "prize_money": _clean(self.prize_money),
            "track_condition": _clean(self.track_condition),
            "comment": _clean(self.comment),
            "url": self.url,
            "field_size": self.field_size,
            "scratchings": self.scratchings,
            **({"raw": self.raw} if self.raw else {}),
            "runners": [r.to_dict() for r in self.runners],
        }


@dataclass
class Meeting:
    """One track's card for one date."""

    track: str | None = None               # display name, e.g. "Ladbrokes Q1 Lakeside"
    track_slug: str | None = None          # URL slug, e.g. "ladbrokes-q1-lakeside"
    state: str | None = None               # NSW / VIC / QLD / SA / WA / TAS / NT
    meeting_date: str | None = None        # YYYY-MM-DD
    url: str | None = None
    race_count: int | None = None
    races: list[Race] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)   # source-specific ids/state

    def to_dict(self) -> dict[str, Any]:
        return {
            "track": _clean(self.track),
            "track_slug": self.track_slug,
            "state": self.state,
            "meeting_date": self.meeting_date,
            "url": self.url,
            "race_count": self.race_count if self.race_count is not None else len(self.races),
            **({"raw": self.raw} if self.raw else {}),
            "races": [r.to_dict() for r in self.races],
        }


@dataclass
class DayCard:
    """Everything scraped for a single racing day."""

    meeting_date: str
    scraped_at: str
    source: str = "thedogs.com.au"
    meetings: list[Meeting] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_races(self) -> int:
        return sum(len(m.races) for m in self.meetings)

    @property
    def total_runners(self) -> int:
        return sum(len(r.runners) for m in self.meetings for r in m.races)

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
            "meetings": [m.to_dict() for m in self.meetings],
            "errors": self.errors,
        }


def card_from_dict(data: dict[str, Any]) -> DayCard:
    """Rebuild a DayCard from a previously written JSON file.

    Lets other tools run against saved output instead of re-fetching,
    which makes replaying a past day free.
    """
    card = DayCard(
        meeting_date=data.get("meeting_date", ""),
        scraped_at=data.get("scraped_at", ""),
        source=data.get("source", "unknown"),
        errors=data.get("errors", []) or [],
    )
    for m in data.get("meetings", []) or []:
        meeting = Meeting(
            track=m.get("track"),
            track_slug=m.get("track_slug"),
            state=m.get("state"),
            meeting_date=m.get("meeting_date"),
            url=m.get("url"),
            race_count=m.get("race_count"),
            raw=m.get("raw") or {},
        )
        for r in m.get("races", []) or []:
            race = Race(
                race_number=r.get("race_number"),
                name=r.get("name"),
                distance_m=r.get("distance_m"),
                grade=r.get("grade"),
                start_time_local=r.get("start_time_local"),
                prize_money=r.get("prize_money"),
                track_condition=r.get("track_condition"),
                comment=r.get("comment"),
                url=r.get("url"),
                raw=r.get("raw") or {},
            )
            for run in r.get("runners", []) or []:
                race.runners.append(Runner(
                    box=run.get("box"),
                    name=run.get("name"),
                    trainer=run.get("trainer"),
                    weight_kg=run.get("weight_kg"),
                    form=run.get("form"),
                    best_time=run.get("best_time"),
                    prize_money=run.get("prize_money"),
                    odds=run.get("odds"),
                    scratched=bool(run.get("scratched")),
                    scratch_time=run.get("scratch_time"),
                    dog_url=run.get("dog_url"),
                    raw=run.get("raw") or {},
                ))
            meeting.races.append(race)
        card.meetings.append(meeting)
    return card


def parse_date(value: str | _date) -> _date:
    """Accept a date object, 'today', 'tomorrow', 'yesterday', or YYYY-MM-DD."""
    from datetime import timedelta
    from .utils.dates import today_local

    if isinstance(value, _date):
        return value
    v = str(value).strip().lower()
    if v == "today":
        return today_local()
    if v == "tomorrow":
        return today_local() + timedelta(days=1)
    if v == "yesterday":
        return today_local() - timedelta(days=1)
    return _date.fromisoformat(v)
