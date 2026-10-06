"""Pairing the two cards up before anything is compared.

Venues are the only genuinely hard part: the same track is `ANGLE PARK` in the
feed and `Angle Park` on thedogs, but also `Q1 LAKESIDE` against
`Ladbrokes Q1 Lakeside`. Three things are tried, in order:

1. the slugified venue name - which already settles most of them,
2. any `AlternateVenueNames` the feed shipped for that meeting, which the
   mapper stores on `Meeting.raw["alternate_names"]`,
3. `track_aliases.yaml`, for the pairs nobody could have guessed.

Whatever still will not pair is reported as `unmatched` with the exact
spelling each side used, so the first run tells you what to add.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dogs_scraper.models import DayCard, Meeting, Race, Runner
from dogs_scraper.utils.text import slugify

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ALIASES = PROJECT_ROOT / "track_aliases.yaml"


def load_aliases(path: str | Path | None = None) -> dict[str, str]:
    """Read `track_aliases.yaml` into {alias slug: canonical slug}.

    The file maps a canonical name to the spellings seen elsewhere:

        angle-park:
          - Angle Park Night
          - ANGLE PARK

    A missing or unparseable file is not an error - the matcher just has less
    to work with, and says so in the report.
    """
    path = Path(path) if path else DEFAULT_ALIASES
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:                                   # pragma: no cover
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}

    aliases: dict[str, str] = {}
    for canonical, spellings in data.items():
        key = slugify(canonical)
        if not key:
            continue
        aliases[key] = key
        for spelling in spellings or []:
            alias = slugify(spelling)
            if alias:
                aliases[alias] = key
    return aliases


#: thedogs prefixes sponsored venues - "Ladbrokes Q Straight" for the track the
#: feed calls "Q Straight". The sponsor changes more often than the track does,
#: so the prefix is stripped when matching rather than chased in the alias file.
SPONSOR_PREFIXES = ("ladbrokes-", "sportsbet-", "tab-", "betr-", "thedogs-")


def _without_sponsor(slug: str) -> str | None:
    for prefix in SPONSOR_PREFIXES:
        if slug.startswith(prefix) and len(slug) > len(prefix):
            return slug[len(prefix):]
    return None


def meeting_keys(meeting: Meeting, aliases: dict[str, str]) -> set[str]:
    """Every slug this meeting could reasonably be known by."""
    keys: set[str] = set()
    for candidate in [meeting.track_slug, meeting.track,
                      *(meeting.raw.get("alternate_names") or [])]:
        slug = slugify(candidate)
        if not slug:
            continue
        for form in (slug, _without_sponsor(slug)):
            if form:
                keys.add(form)
                keys.add(aliases.get(form, form))
    return keys


@dataclass
class MeetingPair:
    key: str
    reference: Meeting
    ours: Meeting


@dataclass
class MatchResult:
    pairs: list[MeetingPair]
    reference_only: list[Meeting]
    ours_only: list[Meeting]

    def unmatched(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "reference_only": [{"track": m.track, "slug": m.track_slug}
                               for m in self.reference_only],
            "ours_only": [{"track": m.track, "slug": m.track_slug}
                          for m in self.ours_only],
        }


def match_cards(reference: DayCard, ours: DayCard,
                aliases: dict[str, str] | None = None) -> MatchResult:
    """Pair meetings across the two cards."""
    aliases = aliases if aliases is not None else load_aliases()

    ours_by_key: dict[str, Meeting] = {}
    for meeting in ours.meetings:
        for key in meeting_keys(meeting, aliases):
            ours_by_key.setdefault(key, meeting)

    pairs: list[MeetingPair] = []
    matched_ours: set[int] = set()
    reference_only: list[Meeting] = []

    for meeting in reference.meetings:
        found = None
        for key in sorted(meeting_keys(meeting, aliases)):
            candidate = ours_by_key.get(key)
            if candidate is not None and id(candidate) not in matched_ours:
                found = (key, candidate)
                break
        if found is None:
            reference_only.append(meeting)
            continue
        key, candidate = found
        matched_ours.add(id(candidate))
        pairs.append(MeetingPair(key=key, reference=meeting, ours=candidate))

    ours_only = [m for m in ours.meetings if id(m) not in matched_ours]
    return MatchResult(pairs=pairs, reference_only=reference_only, ours_only=ours_only)


def match_races(reference: Meeting, ours: Meeting
                ) -> tuple[list[tuple[Race, Race]], list[Race], list[Race]]:
    """Races pair on race number - both sides number them the same way."""
    ours_by_number = {r.race_number: r for r in ours.races if r.race_number is not None}
    paired, reference_only = [], []

    for race in reference.races:
        other = ours_by_number.pop(race.race_number, None)
        if other is None:
            reference_only.append(race)
        else:
            paired.append((race, other))

    return paired, reference_only, list(ours_by_number.values())


def match_runners(reference: Race, ours: Race, max_box: int | None = None
                  ) -> list[tuple[int, Runner | None, Runner | None]]:
    """Runners pair on box - the one value both sides always have.

    Returns every box either side knows about, so a box present on one side
    and absent on the other still comes back (as a None).

    `max_box` drops the reserve rugs above the eighth. The two sources list
    reserves differently and neither is wrong about it, so comparing them
    produces noise rather than findings.
    """
    def boxes_of(race: Race) -> dict[int, Runner]:
        return {r.box: r for r in race.runners
                if r.box and (max_box is None or r.box <= max_box)}

    ref_by_box, our_by_box = boxes_of(reference), boxes_of(ours)
    boxes: Iterable[int] = sorted(set(ref_by_box) | set(our_by_box))
    return [(box, ref_by_box.get(box), our_by_box.get(box)) for box in boxes]
