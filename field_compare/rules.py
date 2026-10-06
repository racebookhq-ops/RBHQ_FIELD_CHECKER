"""The checks, and how much each one matters.

The governing idea:

    A race is correct when the same greyhounds are running on both sides.

It is the **set of active runners** that is compared, by name - not the boxes.
The two sources disagree about boxes constantly and harmlessly: a reserve
promoted into a scratching keeps rug 9 or 10 on one side while the other moves
it straight into the vacated barrier, and both are telling the truth. What
cannot differ is who is in the race. A dog we have a market on that is not
running, or a runner we have no market on, is a real problem; the same dog in a
different box is not.

Three things keep the report honest rather than noisy:

* **Names are normalised before comparing** - upper-cased, punctuation
  stripped - so `O'Reilly's Boy` and `OReillys Boy` are the same dog. Only a
  genuinely different name counts.
* **A field only gets compared when both sides publish it.** The RBHQ feed
  carries no weight, form, best time or price, so those are skipped outright
  instead of being reported as a difference on every runner.
* **A box difference is recorded as info**, never as a finding worth acting
  on - it is there if you want it, and filtered out if you do not.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dogs_scraper.models import DayCard, Race, Runner
from dogs_scraper.utils.dates import now_local
from dogs_scraper.utils.text import normalise_dog_name

from .matcher import MatchResult, match_cards, match_races
from .models import ComparisonReport, Discrepancy, Severity

#: Below this, a start-time difference is clock skew rather than a real change.
START_DRIFT_TOLERANCE_S = 120


def _both(a: Any, b: Any) -> bool:
    """True only when both sides actually published the value."""
    return a is not None and b is not None


def _key(name: str | None) -> str | None:
    return normalise_dog_name(name) or None


def _by_name(race: Race) -> dict[str, Runner]:
    """Every named runner on the card, scratched or not, keyed for matching."""
    found: dict[str, Runner] = {}
    for runner in race.runners:
        key = _key(runner.name)
        # A live entry beats a scratched one of the same name - a dog listed
        # twice through a promotion is in the race.
        if key and (key not in found or (found[key].scratched and not runner.scratched)):
            found[key] = runner
    return found


def _active(by_name: dict[str, Runner]) -> set[str]:
    """The dogs actually due to run."""
    return {k for k, r in by_name.items() if not r.scratched}


def _seconds_apart(a: str | None, b: str | None) -> float | None:
    if not _both(a, b):
        return None
    try:
        return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds())
    except (ValueError, TypeError):
        return None


def _where(track: str | None, race: Race | None) -> dict[str, Any]:
    """The location fields every record carries, so a reader can navigate."""
    return {
        "track": track,
        "race_number": race.race_number if race else None,
        "race_url": race.url if race else None,
        "start_time_local": race.start_time_local if race else None,
    }


# --------------------------------------------------------------------------
# who is in the race - the whole point
# --------------------------------------------------------------------------
def _check_runners(report: ComparisonReport, track: str | None, ref_race: Race,
                   our_race: Race, strict: bool) -> int:
    where = _where(track, ref_race)
    ref_by_name, our_by_name = _by_name(ref_race), _by_name(our_race)
    ref_active, our_active = _active(ref_by_name), _active(our_by_name)
    label = f"{track} R{ref_race.race_number}"

    # Running in the field, but not running on our card.
    for key in sorted(ref_active - our_active):
        dog = ref_by_name[key]
        ours = our_by_name.get(key)
        if ours is None:
            message = f"{label}: {dog.name} is in the field, we do not have it at all"
        else:
            message = f"{label}: {dog.name} is in the field, we have it scratched"
        report.add(Discrepancy(
            type="runner_missing", severity=Severity.CRITICAL, message=message,
            box=dog.box, field="name", reference=dog.name,
            ours=ours.name if ours else None, **where))

    # Running on our card, but not running in the field.
    for key in sorted(our_active - ref_active):
        dog = our_by_name[key]
        ref = ref_by_name.get(key)
        if ref is None:
            message = f"{label}: we have {dog.name} running, it is not in the field"
            kind = "runner_not_in_field"
        else:
            message = f"{label}: {dog.name} is scratched in the field, still running on ours"
            kind = "scratched_still_open"
        report.add(Discrepancy(
            type=kind, severity=Severity.CRITICAL, message=message,
            box=dog.box, field="name", reference=ref.name if ref else None,
            ours=dog.name, **where))

    # Same dog, both running, different box. Recorded because it is cheap to
    # know, not because anything needs doing about it.
    for key in sorted(ref_active & our_active):
        ref, ours = ref_by_name[key], our_by_name[key]
        if _both(ref.box, ours.box) and ref.box != ours.box:
            report.add(Discrepancy(
                type="box_mismatch", severity=Severity.INFO,
                message=f"{label}: {ref.name} is box {ref.box} in the field, "
                        f"box {ours.box} on ours",
                box=ref.box, field="box", reference=ref.box, ours=ours.box, **where))

        if ref.name != ours.name:
            report.add(Discrepancy(
                type="name_spelling", severity=Severity.INFO,
                message=f"{label}: spelled {ref.name!r} in the field, "
                        f"{ours.name!r} on ours",
                box=ref.box, field="name", reference=ref.name, ours=ours.name, **where))

        if strict and _both(ref.trainer, ours.trainer) and \
                _key(ref.trainer) != _key(ours.trainer):
            report.add(Discrepancy(
                type="trainer_mismatch", severity=Severity.INFO,
                message=f"{label}: {ref.name} trained by {ref.trainer} in the "
                        f"field, {ours.trainer} on ours",
                box=ref.box, field="trainer", reference=ref.trainer,
                ours=ours.trainer, **where))

    return len(ref_active | our_active)


# --------------------------------------------------------------------------
# race-level checks
# --------------------------------------------------------------------------
def _check_race(report: ComparisonReport, track: str | None,
                ref_race: Race, our_race: Race, strict: bool) -> int:
    where = _where(track, ref_race)

    if _both(ref_race.distance_m, our_race.distance_m) and \
            ref_race.distance_m != our_race.distance_m:
        report.add(Discrepancy(
            type="distance_mismatch", severity=Severity.WARNING,
            message=f"{track} R{ref_race.race_number}: {ref_race.distance_m}m in "
                    f"the field, {our_race.distance_m}m on ours",
            field="distance_m", reference=ref_race.distance_m,
            ours=our_race.distance_m, **where))

    ref_size = len(_active(_by_name(ref_race)))
    our_size = len(_active(_by_name(our_race)))
    if ref_size != our_size:
        report.add(Discrepancy(
            type="field_size_mismatch", severity=Severity.WARNING,
            message=f"{track} R{ref_race.race_number}: {ref_size} runners in the "
                    f"field, {our_size} on ours",
            field="field_size", reference=ref_size, ours=our_size, **where))

    drift = _seconds_apart(ref_race.start_time_local, our_race.start_time_local)
    if drift is not None and drift > START_DRIFT_TOLERANCE_S:
        report.add(Discrepancy(
            type="start_time_drift", severity=Severity.INFO,
            message=f"{track} R{ref_race.race_number}: start times differ by "
                    f"{int(drift // 60)} min",
            field="start_time_local", reference=ref_race.start_time_local,
            ours=our_race.start_time_local, **where))

    return _check_runners(report, track, ref_race, our_race, strict)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def compare_cards(reference: DayCard, ours: DayCard, *, strict: bool = False,
                  aliases: dict[str, str] | None = None) -> ComparisonReport:
    """Check `ours` against the published field in `reference`."""
    report = ComparisonReport(
        meeting_date=reference.meeting_date or ours.meeting_date,
        generated_at=now_local().isoformat(),
        reference_source=reference.source,
        our_source=ours.source,
    )

    match: MatchResult = match_cards(reference, ours, aliases)
    races_compared = runners_compared = 0

    for meeting in match.reference_only:
        report.add(Discrepancy(
            type="meeting_missing", severity=Severity.CRITICAL,
            message=f"{meeting.track} is racing on thedogs ({len(meeting.races)} "
                    f"races) and is missing from our card",
            track=meeting.track, reference=meeting.track, ours=None))

    for meeting in match.ours_only:
        report.add(Discrepancy(
            type="meeting_unexpected", severity=Severity.WARNING,
            message=f"{meeting.track} is on our card but not on thedogs - "
                    f"usually a missing track alias",
            track=meeting.track, reference=None, ours=meeting.track))

    for pair in match.pairs:
        track = pair.reference.track
        paired, ref_only, our_only = match_races(pair.reference, pair.ours)

        for race in ref_only:
            report.add(Discrepancy(
                type="race_missing", severity=Severity.CRITICAL,
                message=f"{track} R{race.race_number} is on thedogs and missing "
                        f"from our card",
                **_where(track, race)))

        for race in our_only:
            report.add(Discrepancy(
                type="race_unexpected", severity=Severity.WARNING,
                message=f"{track} R{race.race_number} is on our card but not on "
                        f"thedogs",
                track=track, race_number=race.race_number))

        for ref_race, our_race in paired:
            runners_compared += _check_race(report, track, ref_race, our_race, strict)
            races_compared += 1

    report.stats = {
        "meetings_matched": len(match.pairs),
        "races_compared": races_compared,
        "runners_compared": runners_compared,
        "matched_on": "runner name",
        "strict": strict,
        "unmatched": match.unmatched(),
    }
    return report
