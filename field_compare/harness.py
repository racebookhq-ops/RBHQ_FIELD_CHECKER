"""Check the RBHQ harness fields against harness.org.au.

    reference = harness.org.au   (harness_scraper)       - the published field
    ours      = the RBHQ feed    (rbhq_scraper --harness) - what we are taking bets on

Harness has no boxes, so a runner is identified by **horse name within a race
number**. Three questions, in the order they matter:

1. **Does the race exist?**   RBHQ has race 9 but the official site stops at
   race 8 -> `race_unexpected` (critical: we have a market on a race that is not
   being run). The reverse -> `race_missing` (critical).
2. **Is the runner in the field?**   An active horse in the official field that
   we do not have (or have scratched) -> `runner_missing`; one we have running
   that the official field does not -> `runner_not_in_field` /
   `scratched_still_open`. All critical. A missing/extra pair that is plainly the
   same horse under a damaged name ("Pencil Me" for "Pencil Me In") becomes one
   `name_mismatch` (warning).
3. **Is the runner in the right race?**   The same horse is running in a
   different race number on each side -> `wrong_race` (critical). One finding
   replaces the missing/not-in-field pair it would otherwise cause.

Only active runners count: a scratched horse is not "in the field". Meetings that
cannot be paired are reported with the spelling each side used, so the first run
shows what to add to `harness_track_aliases.yaml`.

NOT compared: boxes/barriers (none), times, distances, trainers and drivers.
RBHQ's harness field mapping is unverified (see rbhq_scraper/harness_mapper.py),
so a flood of findings on a first real run can mean the mapping, not the feed.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dogs_scraper.utils.dates import now_local
from dogs_scraper.utils.text import slugify
from harness_scraper.models import DayCard, Meeting, Race, Runner

from .models import ComparisonReport, Discrepancy, Severity

DEFAULT_HARNESS_ALIASES = Path(__file__).resolve().parent.parent / "harness_track_aliases.yaml"

#: Imported horses carry a country tag that one source may drop: "Final Deadline NZ".
_COUNTRY_SUFFIX = re.compile(r"[\s(]+(nz|usa|us|can|ire|gb|aus|swe|fra)\)?$", re.I)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def horse_key(name: str | None) -> str | None:
    """Comparable form of a horse name: case, punctuation and country tag ignored."""
    if not name:
        return None
    text = _COUNTRY_SUFFIX.sub("", name.strip())
    return _NON_ALNUM.sub("", text.lower()) or None


def _same_horse(ref: Runner, ours: Runner, ref_key: str, our_key: str) -> bool:
    """Two unmatched names in one race that are plausibly the same horse.

    One name is the start of the other ("Pencil Me" / "Pencil Me In" - the RBHQ
    feed has been seen dropping the last word), or the saddlecloth agrees and
    the names are close.
    """
    if ref_key.startswith(our_key) or our_key.startswith(ref_key):
        return True
    return (ref.saddlecloth is not None and ref.saddlecloth == ours.saddlecloth
            and SequenceMatcher(None, ref_key, our_key).ratio() >= 0.7)


# --------------------------------------------------------------------------
# pairing meetings
# --------------------------------------------------------------------------
def _meeting_keys(m: Meeting, aliases: dict[str, str]) -> set[str]:
    keys: set[str] = set()
    for candidate in (m.track_name, m.track_slug):
        slug = slugify(candidate)
        if slug:
            keys.add(slug)
            keys.add(aliases.get(slug, slug))
    return keys


@dataclass
class _Pair:
    reference: Meeting
    ours: Meeting


def _match_meetings(reference: DayCard, ours: DayCard, aliases: dict[str, str]
                    ) -> tuple[list[_Pair], list[Meeting], list[Meeting]]:
    by_key: dict[str, Meeting] = {}
    for m in ours.meetings:
        for k in _meeting_keys(m, aliases):
            by_key.setdefault(k, m)

    pairs, ref_only, used = [], [], set()
    for m in reference.meetings:
        hit = next((by_key[k] for k in sorted(_meeting_keys(m, aliases))
                    if k in by_key and id(by_key[k]) not in used), None)
        if hit is None:
            ref_only.append(m)
        else:
            used.add(id(hit))
            pairs.append(_Pair(m, hit))
    return pairs, ref_only, [m for m in ours.meetings if id(m) not in used]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _by_key(race: Race) -> dict[str, Runner]:
    """Named runners keyed for matching; a live entry beats a scratched duplicate."""
    found: dict[str, Runner] = {}
    for r in race.runners:
        k = horse_key(r.horse)
        if k and (k not in found or (found[k].scratched and not r.scratched)):
            found[k] = r
    return found


def _placements(meeting: Meeting) -> dict[str, dict[int, Runner]]:
    """horse key -> {race_no: runner} for every ACTIVE runner in the meeting."""
    out: dict[str, dict[int, Runner]] = {}
    for race in meeting.races:
        if race.race_no is None:
            continue
        for k, r in _by_key(race).items():
            if not r.scratched:
                out.setdefault(k, {})[race.race_no] = r
    return out


def _where(track: str | None, race: Race | None, race_no: int | None = None) -> dict[str, Any]:
    return {
        "track": track,
        "race_number": race.race_no if race else race_no,
        "race_url": race.url if race else None,
        "start_time_local": race.start_time if race else None,
    }


# --------------------------------------------------------------------------
# one meeting
# --------------------------------------------------------------------------
def _compare_meeting(report: ComparisonReport, pair: _Pair) -> tuple[int, int]:
    track = pair.reference.track_name or pair.ours.track_name
    ref_races = {r.race_no: r for r in pair.reference.races if r.race_no is not None}
    our_races = {r.race_no: r for r in pair.ours.races if r.race_no is not None}

    # 1. does the race exist?
    for no in sorted(set(ref_races) - set(our_races)):
        report.add(Discrepancy(
            type="race_missing", severity=Severity.CRITICAL,
            message=f"{track} R{no} is on harness.org.au and missing from our card",
            **_where(track, ref_races[no])))
    for no in sorted(set(our_races) - set(ref_races)):
        last = max(ref_races) if ref_races else None
        extra = f" (the official card stops at R{last})" if last else " (the official card has no races)"
        report.add(Discrepancy(
            type="race_unexpected", severity=Severity.CRITICAL,
            message=f"{track} R{no} is on our card but not on harness.org.au{extra}",
            **_where(track, our_races[no])))

    # 3. is the runner in the right race? Decided first so it can absorb the
    #    missing / not-in-field findings it would otherwise cause twice over.
    ref_pl, our_pl = _placements(pair.reference), _placements(pair.ours)
    explained: set[tuple[str, int]] = set()
    for key in sorted(set(ref_pl) & set(our_pl)):
        only_ours = set(our_pl[key]) - set(ref_pl[key])
        only_ref = set(ref_pl[key]) - set(our_pl[key])
        if not (only_ours and only_ref):
            continue
        official = ", ".join(f"R{n}" for n in sorted(only_ref))
        for no in sorted(only_ours):
            runner = our_pl[key][no]
            report.add(Discrepancy(
                type="wrong_race", severity=Severity.CRITICAL,
                message=f"{track}: {runner.horse} is in R{no} on ours but in {official} "
                        f"on harness.org.au",
                field="race_number", reference=sorted(only_ref), ours=no,
                **_where(track, our_races.get(no), no)))
            explained.add((key, no))
        explained.update((key, n) for n in only_ref)

    # 2. is the runner in the field? Races present on both sides only.
    runners_compared = 0
    for no in sorted(set(ref_races) & set(our_races)):
        ref_race, our_race = ref_races[no], our_races[no]
        where = _where(track, ref_race)
        ref_by, our_by = _by_key(ref_race), _by_key(our_race)
        ref_active = {k for k, r in ref_by.items() if not r.scratched}
        our_active = {k for k, r in our_by.items() if not r.scratched}
        label = f"{track} R{no}"

        missing = [k for k in sorted(ref_active - our_active) if (k, no) not in explained]
        extra = [k for k in sorted(our_active - ref_active) if (k, no) not in explained]

        # The same horse under a damaged name is one finding, not a missing
        # runner plus an unknown one.
        for mk in list(missing):
            ek = next((e for e in extra if _same_horse(ref_by[mk], our_by[e], mk, e)), None)
            if ek is None:
                continue
            missing.remove(mk)
            extra.remove(ek)
            ref_dog, our_dog = ref_by[mk], our_by[ek]
            report.add(Discrepancy(
                type="name_mismatch", severity=Severity.WARNING,
                message=f"{label}: official name is {ref_dog.horse!r}, ours is {our_dog.horse!r}",
                field="horse", reference=ref_dog.horse, ours=our_dog.horse, **where))

        for key in missing:
            dog, ours = ref_by[key], our_by.get(key)
            how = "we have it scratched" if ours else "we do not have it at all"
            report.add(Discrepancy(
                type="runner_missing", severity=Severity.CRITICAL,
                message=f"{label}: {dog.horse} is in the field, {how}",
                field="horse", reference=dog.horse, ours=ours.horse if ours else None, **where))

        for key in extra:
            dog, ref = our_by[key], ref_by.get(key)
            if ref is None:
                kind, msg = "runner_not_in_field", f"{label}: we have {dog.horse} running, it is not in the field"
            else:
                kind, msg = "scratched_still_open", f"{label}: {dog.horse} is scratched on harness.org.au, still running on ours"
            report.add(Discrepancy(
                type=kind, severity=Severity.CRITICAL, message=msg,
                field="horse", reference=ref.horse if ref else None, ours=dog.horse, **where))

        runners_compared += len(ref_active | our_active)
    return len(set(ref_races) & set(our_races)), runners_compared


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def compare_harness(reference: DayCard, ours: DayCard, *,
                    aliases: dict[str, str] | None = None) -> ComparisonReport:
    """Check `ours` (RBHQ) against `reference` (harness.org.au)."""
    report = ComparisonReport(
        meeting_date=reference.meeting_date or ours.meeting_date,
        generated_at=now_local().isoformat(),
        reference_source=reference.source,
        our_source=ours.source,
    )
    pairs, ref_only, ours_only = _match_meetings(reference, ours, aliases or {})

    for m in ref_only:
        report.add(Discrepancy(
            type="meeting_missing", severity=Severity.CRITICAL,
            message=f"{m.track_name} is racing on harness.org.au ({len(m.races)} races) "
                    f"and is missing from our card",
            track=m.track_name, reference=m.track_name))
    for m in ours_only:
        report.add(Discrepancy(
            type="meeting_unexpected", severity=Severity.WARNING,
            message=f"{m.track_name} is on our card but not on harness.org.au - "
                    f"a trial, or a missing track alias",
            track=m.track_name, ours=m.track_name))

    races = runners = 0
    for pair in pairs:
        r, n = _compare_meeting(report, pair)
        races += r
        runners += n

    report.stats = {
        "meetings_matched": len(pairs),
        "races_compared": races,
        "runners_compared": runners,
        "matched_on": "horse name + race number",
        "unmatched": {
            "reference_only": [{"track": m.track_name, "slug": m.track_slug} for m in ref_only],
            "ours_only": [{"track": m.track_name, "slug": m.track_slug} for m in ours_only],
        },
    }
    return report
